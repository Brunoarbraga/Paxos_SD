import socket
import time
import random
import json
from constants import *

class Cliente:
    def __init__(self, host, porta, id = 1) -> None:
        self.id = id
        self.host = host # ip
        self.porta = porta # porta
        self.num_requisicoes = random.randint(1, 1) # número aleatório de requisições
    
    def enviar_requisicao(self, connection):
        # Obtém o timestamp e envia para o nó 
        timestamp = time.time_ns() # retorna o tempo em nanossegundos como um inteiro
        valor = random.randint(1, 10000) # valor aleatório da requisição
        mensagem = {"timestamp": timestamp, "valor": valor}
        mensagem = json.dumps(mensagem)
        print(f"Cliente {self.id} enviando requisição para o nó com timestamp {timestamp} e valor {valor}")
        connection.sendall(mensagem.encode())

    def esperar_resposta(self, connection):
        # Espera a resposta do nó e exibe-a
        try:
            resposta = connection.recv(BUFFER_SIZE)
            
            if not resposta: # se a resposta estiver vazia, a conexão foi fechada
                print(f"\033[31mCliente {self.id}: conexão fechada pelo servidor.\033[0m")
                return
            
            resposta = json.loads(resposta.decode())
            # print(f"Cliente {self.id} recebeu {resposta['status']} do host {self.host}")
        
        except ConnectionResetError:
            print(f"\033[31mCliente {self.id}: conexão resetada pelo servidor.\033[0m")
        except Exception as e:
            print(f"\033[31mErro ao receber resposta: {e}\033[0m")

    def ficar_ocioso(self):
        tempo = random.uniform(1, 5)
        print(f"Cliente {self.id} em espera por {tempo} segundos")
        time.sleep(tempo)

    def __call__(self):
        connection = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            connection.connect((self.host, self.porta))
            # print(f"Conectado ao nó {self.porta}")
            for _ in range(self.num_requisicoes):
                self.enviar_requisicao(connection)
                self.esperar_resposta(connection)
                self.ficar_ocioso()
        except Exception as e:
            print(f"\033[31mErro na comunicação: {e}\033[0m")
        finally:
            connection.close()

if __name__ == "__main__":
    import sys
    
    if len(sys.argv) != 4:
        print("Uso: python3 client.py <id_cliente> <host> <porta_no>")
        sys.exit(1)

    id_cliente = sys.argv[1]
    host = sys.argv[2]
    porta_no = int(sys.argv[3])
    
    cliente = Cliente(
        id = id_cliente,
        host = host,
        porta = porta_no
    )

    cliente()
