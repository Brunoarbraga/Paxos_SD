import socket
import time
import random
import json
from constants import *

class Cliente:
    def __init__(self, host, porta_no, porta_client, id=1) -> None:
        self.id = id
        self.host = host  # ip
        self.porta_no = porta_no  # porta do nó
        self.porta_client = porta_client  # porta do cliente
        self.commits_recebidos = 0
        self.num_requisicoes = random.randint(3, 3)  # número aleatório de requisições

        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.bind((self.host, self.porta_client))
        self.server_socket.listen()

    # Obtém o timestamp e envia para o nó
    def enviar_requisicao(self, connection):
        timestamp = time.time_ns()  # retorna o tempo em nanossegundos como um inteiro
        valor = random.randint(1, 10000)  # valor aleatório da requisição
        mensagem = {
            "tipo": "request",
            "timestamp": timestamp,
            "valor": valor,
            "client_id": self.id,
            "client_port": self.porta_client,
            "client_host": self.host
        }
        mensagem = json.dumps(mensagem)
        print(f"Cliente {self.id} enviando requisição para o nó com timestamp {timestamp} e valor {valor}")
        connection.sendall(mensagem.encode())

    # Espera a resposta do nó e a exibe
    def esperar_resposta(self):
        self.commits_recebidos = 0

        try:
            while self.commits_recebidos < NUMERO_LEARNERS:
                client_socket, client_address = self.server_socket.accept()
                print(f"Conexão recebida de {client_address}")

                resposta = client_socket.recv(1024)

                if not resposta:  # se a resposta estiver vazia, a conexão foi fechada
                    print(f"\033[31mCliente {self.id}: conexão fechada pelo servidor.\033[0m")
                    return

                resposta = json.loads(resposta.decode())
                print(f"Cliente {self.id} recebeu: {resposta['status']}. Transação confirmada no valor de {resposta['valor']}.")

                client_socket.close()
                self.commits_recebidos += 1

        except ConnectionResetError:
            print(f"\033[31mCliente {self.id}: conexão resetada pelo servidor.\033[0m")
        except Exception as e:
            print(f"\033[31mErro ao receber resposta: {e}\033[0m")

    # O cliente fica em espera
    def ficar_ocioso(self):
        tempo = random.uniform(1, 1)
        print(f"Cliente {self.id} em espera por {tempo} segundos")
        time.sleep(tempo)

    def __call__(self):
        # conexão com o proposer
        connection = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

        try:
            connection.connect((self.host, self.porta_no))

            for _ in range(self.num_requisicoes):
                self.enviar_requisicao(connection)
                self.esperar_resposta()
                self.ficar_ocioso()

        except Exception as e:
            print(f"\033[31mErro na comunicação: {e}\033[0m")
        finally:
            connection.close()

if __name__ == "__main__":
    import sys

    if len(sys.argv) != 5:
        print("Uso: python3 client.py <id_cliente> <porta_que_escuta> <host> <porta_no>")
        sys.exit(1)

    id_cliente = sys.argv[1]
    porta_para_escutar = int(sys.argv[2])
    host = sys.argv[3]
    porta_para_mandar = int(sys.argv[4])

    cliente = Cliente(
        id=id_cliente,
        porta_client=porta_para_escutar,
        host=host,
        porta_no=porta_para_mandar
    )

    cliente()