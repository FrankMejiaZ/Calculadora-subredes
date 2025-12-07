import ipaddress
import csv
import os
from tabulate import tabulate

class SubnetCalculator:
    def __init__(self):
        self.results = []

    def calculate_subnet_details(self, ip_input, prefix=None):
        """Calcula y muestra los detalles de una red (IPv4/IPv6)."""
        try:
            if prefix:
                network = ipaddress.ip_network(f"{ip_input}/{prefix}", strict=False)
            else:
                network = ipaddress.ip_network(ip_input, strict=False)
            
            version = network.version
            is_ipv4 = version == 4
            
            # Definir atributos según versión
            if is_ipv4:
                netmask = network.netmask
                broadcast = network.broadcast_address
                total_hosts = network.num_addresses
                # Para redes /31 y /32 no hay hosts útiles de la forma estándar
                if total_hosts > 2:
                    first_ip = list(network.hosts())[0]
                    last_ip = list(network.hosts())[-1]
                    usable_hosts = total_hosts - 2
                else:
                    first_ip = "N/A"
                    last_ip = "N/A"
                    usable_hosts = 0
            else:
                # IPv6
                netmask = network.prefixlen  # En IPv6 se usa más el prefijo
                broadcast = "N/A (IPv6 usa Multicast)"
                total_hosts = network.num_addresses
                # IPv6 tiene demasiados hosts para listar, mostramos rango teórico
                first_ip = network.network_address + 1
                last_ip = network.broadcast_address - 1 # Teórico
                usable_hosts = "Indeterminado (enorme)"

            data = [
                ["Versión IP", f"IPv{version}"],
                ["Dirección de Red", network.network_address],
                ["Prefijo / Máscara", f"/{network.prefixlen} ({netmask})"],
                ["Total de Direcciones", total_hosts],
                ["Hosts Útiles", usable_hosts],
                ["Primera IP Útil", first_ip],
                ["Última IP Útil", last_ip],
                ["Dirección de Broadcast", broadcast]
            ]
            
            print(f"\n--- Detalles de la Red {network} ---")
            print(tabulate(data, headers=["Parámetro", "Valor"], tablefmt="fancy_grid"))
            return network
            
        except ValueError as e:
            print(f"Error: {e}")
            return None

    def subnet_by_hosts(self, ip_input, num_hosts):
        """Divide una red en subredes de tamaño fijo según hosts requeridos."""
        try:
            # Asumimos prefijo base /32 para IPv4 si no se da, pero necesitamos una red base.
            # Mejor pedir la red base completa.
            base_network = ipaddress.ip_network(ip_input, strict=False)
            max_bits = 32 if base_network.version == 4 else 128
            
            # Calcular prefijo necesario
            # 2^(max_bits - new_prefix) - 2 >= num_hosts
            # Encontrar el menor prefijo que cumpla
            new_prefix = max_bits
            while True:
                total_addrs = 2 ** (max_bits - new_prefix)
                usable = total_addrs - 2 if base_network.version == 4 else total_addrs - 1 # IPv6 rules vary, simple approx
                if usable >= num_hosts:
                    break
                new_prefix -= 1
                if new_prefix < base_network.prefixlen:
                     print(f"Error: La red base {base_network} es demasiado pequeña para {num_hosts} hosts.")
                     return []

            # Generar subredes
            subnets = list(base_network.subnets(new_prefix=new_prefix))
            
            print(f"\n Se generaron {len(subnets)} subredes /{new_prefix} para soportar {num_hosts} hosts c/u:")
            
            table_data = []
            for idx, sub in enumerate(subnets, 1):
                net_str = str(sub)
                range_str = "N/A"
                broadcast_str = "N/A"
                
                if sub.version == 4:
                    broadcast_str = str(sub.broadcast_address)
                    if sub.num_addresses > 2:
                        range_str = f"{sub.network_address + 1} - {sub.broadcast_address - 1}"
                elif sub.version == 6:
                    range_str = f"{sub.network_address + 1}..."
                
                table_data.append([idx, net_str, range_str, broadcast_str])
                
            print(tabulate(table_data, headers=["#", "ID Red", "Rango Útil", "Broadcast"], tablefmt="simple"))
            
            self.results = subnets # Guardar para exportar
            return subnets

        except ValueError as e:
             print(f"Error: {e}")
             return []

    def calculate_vlsm(self, base_ip_input, hosts_list):
        """Calcula VLSM para una lista de requerimientos de hosts."""
        try:
            base_network = ipaddress.ip_network(base_ip_input, strict=False)
            max_bits = 32 if base_network.version == 4 else 128
            
            # Ordenar requerimientos de mayor a menor
            hosts_list.sort(reverse=True)
            
            print(f"\n--- Cálculo VLSM para {base_network} ---")
            print(f"Requerimientos ordenados: {hosts_list}")
            
            current_ip = base_network.network_address
            vlsm_results = []
            
            for req_hosts in hosts_list:
                # Calcular prefijo para este requerimiento
                prefix = max_bits
                while True:
                    size = 2**(max_bits - prefix)
                    usable = size - 2 if base_network.version == 4 else size
                    if usable >= req_hosts:
                        break
                    prefix -= 1
                
                # Crear la subred
                try:
                    subnet = ipaddress.ip_network(f"{current_ip}/{prefix}", strict=False)
                except ValueError:
                    print(f"Error: No hay suficiente espacio en la red base para {req_hosts} hosts.")
                    break
                
                # Verificar si se sale de la red base
                if not subnet.subnet_of(base_network):
                     print(f"Error: Se agotó el espacio de la red base al intentar asignar {req_hosts} hosts.")
                     break

                vlsm_results.append({
                    "Hosts Req": req_hosts,
                    "Subred": str(subnet),
                    "Máscara": str(subnet.netmask) if base_network.version == 4 else f"/{prefix}",
                    "Hosts Disp": usable
                })
                
                # Avanzar a la siguiente IP disponible (siguiente bloque del mismo tamaño)
                # Ojo: la siguiente subred empieza donde termina esta.
                # subnet.broadcast_address + 1 es la siguiente IP.
                next_ip_int = int(subnet.broadcast_address) + 1
                current_ip = ipaddress.ip_address(next_ip_int)

            # Mostrar tabla
            headers = ["Hosts Req", "Subred", "Máscara", "Hosts Disp"]
            rows = [[r["Hosts Req"], r["Subred"], r["Máscara"], r["Hosts Disp"]] for r in vlsm_results]
            print(tabulate(rows, headers=headers, tablefmt="fancy_grid"))
            
            self.results = vlsm_results # Guardar para exportar (formato dict)
            return vlsm_results

        except Exception as e:
            print(f"Error inesperado en VLSM: {e}")
            return []

    def export_csv(self, filename="resultados_subredes.csv"):
        """Exporta los últimos resultados a CSV."""
        if not self.results:
            print("No hay resultados para exportar.")
            return

        try:
            with open(filename, "w", newline="") as f:
                writer = csv.writer(f)
                
                # Detectar tipo de resultado (lista de redes o dicts de VLSM)
                if isinstance(self.results[0], (ipaddress.IPv4Network, ipaddress.IPv6Network)):
                    writer.writerow(["Subred", "Prefijo", "Num Hosts"])
                    for net in self.results:
                        writer.writerow([str(net), net.prefixlen, net.num_addresses])
                elif isinstance(self.results[0], dict):
                    keys = self.results[0].keys()
                    writer.writerow(keys)
                    for item in self.results:
                        writer.writerow(item.values())
            
            print(f"Resultados exportados a '{filename}'.")
        except Exception as e:
            print(f"Error al exportar: {e}")

# --- Funciones de Ayuda ---

def get_valid_input(prompt, type_func=str):
    while True:
        try:
            val = input(prompt)
            if not val.strip(): continue
            return type_func(val)
        except ValueError:
            print("Entrada inválida. Intente de nuevo.")

def main():
    calc = SubnetCalculator()
    
    while True:
        print("\n --- CALCULADORA DE SUBREDES --- ")
        print("1. Detalles de una Red (IPv4/IPv6)")
        print("2. Subneteo Básico (Tamaño Fijo)")
        print("3. Subneteo VLSM (Tamaño Variable)")
        print("4. Exportar últimos resultados a CSV")
        print("5. Salir")
        
        opcion = input(" Seleccione una opción: ")
        
        if opcion == "1":
            ip = input("Ingrese IP/CIDR (ej. 192.168.1.0/24 o 2001:db8::/32): ")
            calc.calculate_subnet_details(ip)
            
        elif opcion == "2":
            ip = input("Ingrese Red Base (ej. 10.0.0.0/8): ")
            hosts = get_valid_input("Cantidad de hosts por subred: ", int)
            calc.subnet_by_hosts(ip, hosts)
            
        elif opcion == "3":
            ip = input("Ingrese Red Base para VLSM (ej. 192.168.1.0/24): ")
            print("Ingrese las cantidades de hosts separadas por coma (ej. 100, 50, 20):")
            hosts_str = input("> ")
            try:
                hosts_list = [int(x.strip()) for x in hosts_str.split(",")]
                calc.calculate_vlsm(ip, hosts_list)
            except ValueError:
                print(" Error: Lista de hosts inválida.")
                
        elif opcion == "4":
            calc.export_csv()
            
        elif opcion == "5":
            print(" Hasta luego.")
            break
        else:
            print(" Opción no válida.")

if __name__ == "__main__":
    main()
