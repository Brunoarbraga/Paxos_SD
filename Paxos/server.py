from enum import Enum
import socket
import threading
import time
import json
from constants import *

# Define o tipo do nó
class TipoNo (Enum):
    ACCEPTOR = 1
    LEARNER = 2
    CLIENTE = 3

class NoP2P:
    def __init__(self, id, role, host, porta_para_nos, porta_para_clientes, vizinhos, barrier, porta_cliente):
        """
        host: endereço IP do nó atual.
        porta: porta do nó atual.
        vizinhos: lista (host, porta) dos 4 nós vizinhos.
        """
        self.id = id
        self.role = role # TipoNo
        self.host = host
        self.porta_para_outros_nos = porta_para_nos
        self.porta_para_clientes = porta_para_clientes
        self.vizinhos = vizinhos # Lista de 4 vizinhos (host, porta)
        self.sockets_ativos = [] # Lista de conexões ativas
        self.sockets_para_envio = []
        self.barrier = barrier # Barrier para sincronização
        self.porta_cliente = porta_cliente
        self.preparacao_enviada = False
        self.TID = 1 # Valor de transação único que será utilizado para prometer ou não, incrementa caso não for prometido 
        self.valor = None

        self.consenso = 2 # Valor pra atingir um consenso, como existem 3 nós, o consenso é 2 
        self.preparacoes_enviadas = 0
        self.respostas_recebidas = 0

        self.promised_flag = False
        self.promised_value = None
        self.promises_recebidos = 0

        # Cria socket para escutar conexões
        self.servidor_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.servidor_socket.bind((self.host, self.porta_para_outros_nos))
        self.servidor_socket.listen() # até 4 conexões simultâneas


    def preparacao(self, mensagem):
        """ Envia uma mensagem para todos os vizinhos conectados """

        for element in self.sockets_para_envio:

            # Impede que a mensagem seja enviada para um learner
            if element['role'] == TipoNo.LEARNER:
                continue

            # Envia a mensagem codificada
            try:
                element['socket'].send(mensagem)
                self.preparacoes_enviadas = self.preparacoes_enviadas + 1
                print(f"Nó {self.id} enviando preparação: {mensagem}")

            except Exception as e:
                print(f"\033[31mErro ao enviar preparação: {e}\033[0m")
        
        # Aguarda as respostas dos promises que mandou
        while self.respostas_recebidas != self.preparacoes_enviadas:
            for element in self.sockets_para_envio:
                try:
                    tupla_de_resposta = element['socket'].recv(BUFFER_SIZE)

                    if not tupla_de_resposta:
                        continue

                    tupla_de_resposta = json.loads(tupla_de_resposta.decode())

                    if tupla_de_resposta[0] == "promise":
                        print(f"\033[32mNó {self.id} recebeu promise de preparação do nó: {element['id']}\033[0m")
                        self.promises_recebidos += 1

                    else:
                        

                    self.respostas_recebidas += 1
                except Exception as e:
                    print(f"\033[31mErro ao receber resposta: {e}\033[0m")

        self.preparacoes_enviadas = 0
        self.respostas_recebidas = 0













    def receber_preparacao(self):
        """ Recebe mensagens de preparação dos outros nós """
        
        while True:
            for element in self.sockets_ativos:
                try:
                    # Recebe a mensagem
                    dados = element['socket'].recv(BUFFER_SIZE)
                    if not dados:
                        continue

                    # Decodifica a mensagem
                    mensagem = json.loads(dados.decode())
                    print(f"\033[33mNó {self.id} recebeu preparação: {mensagem}\033[0m")

                    # Se não tiver prometido nenhum valor ainda, promete esse
                    if self.promised_flag == False or self.TID < mensagem['TID']:
                        self.prometer_preparacao(element, mensagem)
                    else:
                        self.negar_preparacao(element, mensagem)

                except Exception as e:
                    print(f"\033[31mErro ao receber preparação: {e}\033[0m")
                    continue
                    
            # time.sleep(0.1)
    
    # Devolve um "promise"
    def prometer_preparacao(self, element, mensagem):
        self.promised_flag = True
        self.TID = mensagem['TID'] # atualiza o TID com o TID da mensagem maior
        print(f"\033[32mNó {self.id} prometeu preparação: {mensagem}\033[0m")
        
        mensagem_tupla = (("promise", mensagem))
        # Manda de volta a mensagem com um promise 
        try:
            element['socket'].send((json.dumps(mensagem_tupla)).encode())
        except Exception as e:
            print(f"\033[31mErro ao enviar promise: {e}\033[0m")
    
    # Devolve um "not promise"
    def negar_preparacao(self, element, mensagem):
        print(f"\033[31mNó {self.id} negou preparação: {mensagem}\033[0m")

        mensagem_tupla = (("not promise", mensagem))
        # Manda de volta a mensagem com um not promise 
        try:
            element['socket'].send((json.dumps(mensagem_tupla)).encode())
        except Exception as e:
            print(f"\033[31mErro ao enviar not promise: {e}\033[0m")

    def conectar_com_clientes(self):
        """ Conecta-se a um cliente externo """
        self.barrier.wait()
        self.cliente_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.cliente_socket.bind((self.host, self.porta_para_clientes))
        self.cliente_socket.listen()

        conn, addr = self.cliente_socket.accept()
        print(f"Nó {self.id} conectado com o cliente {addr}")

        # Loop que recebe requisições do cliente
        while True:

            # Recebe requisiçãosockets_ativos
            dados = conn.recv(BUFFER_SIZE)

            if not dados:
                break    

            # Converte o json de volta em dicionário
            mensagem = json.loads(dados.decode())

            # Adicion o TID desse proposer
            mensagem["TID"] = self.TID
            mensagem["ID"] = self.id

            timestamp = mensagem.get('timestamp')
            print(f"\033[33mNó {self.id} recebeu request do cliente com timestamp {timestamp}\033[0m")

            # Converte de novo para json para mandar na preparação
            json_string = json.dumps(mensagem)
            json_string = json_string.encode()

            self.preparacao(json_string)

            # Mandando preparação para os accepters
            # self.preparacao(dados)
            
            # Mensagem de commit
            conn.sendall(json.dumps({"status": "committed", "node_id": self.id, "timestamp": timestamp}).encode())
    
    def conectar_a_vizinhos(self):
        """ Conecta-se a 4 vizinhos usando sockets clientes """
        self.barrier.wait()
        
        for vizinho in self.vizinhos:
            # Impede que um nó se conecte com ele mesmo
            if self.id == vizinho['id']:
                continue
            # Impede que dois learnes se conectem
            if self.role == TipoNo.LEARNER and vizinho['role'] == TipoNo.LEARNER: 
                continue
            
            while True:
                try:               
                    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    sock.settimeout(10) # timeout para evitar bloqueio infinito
                    sock.connect(vizinho['ip_porta'])

                    sock.send(json.dumps({"id": self.id}).encode())

                    self.sockets_ativos.append({"id" : vizinho['id'], "socket" : sock, "role": vizinho['role'], "recebeu_prep" : False})
                    print(f"Nó {self.id} conectado ao vizinho {vizinho['id']} - {vizinho['role']}")
                    break # se a conexão for bem sucedida, sai do loop
                
                except Exception as e:
                    print(f"\033[31mErro ao conectar com {vizinho}: {e}. Tentando novamente em 2s...\033[0m")
                    time.sleep(2)

    def aceitar_conexoes_vizinhos(self):
        """ Escuta conexões dos outros nós """
        self.barrier.wait()
        while True:
            try:
                cliente_socket, addr = self.servidor_socket.accept()

                dados = cliente_socket.recv(BUFFER_SIZE)
                if not dados:
                    continue
                mensagem = json.loads(dados.decode())
                neighbor_id = mensagem.get('id')

                for vizinho in self.vizinhos:
                    if vizinho['id'] == neighbor_id:
                        # Adiciona o socket e o papel do vizinho à lista de envio
                        self.sockets_para_envio.append({
                            "id": vizinho['id'],
                            "socket": cliente_socket,
                            "role": vizinho['role']
                    })
                
            except Exception as e:
                print(f"\033[31mErro ao aceitar conexão: {e}\033[0m")
                break

    def iniciar(self):
        """ Inicia o nó: conecta-se aos vizinhos e aceita conexões """
        threading.Thread(target=self.conectar_a_vizinhos).start()
        threading.Thread(target=self.aceitar_conexoes_vizinhos).start()
        if self.id == 1:
            threading.Thread(target=self.conectar_com_clientes).start()
        threading.Thread(target=self.receber_preparacao).start()

# ---------- Área de teste ----------

barrier = threading.Barrier(3)

# Inicializa o vetor de nós
nos = [{"id": 1, "role" : TipoNo.ACCEPTOR , "ip_porta" : ("127.0.0.1", 5000)},
       {"id": 2, "role" : TipoNo.ACCEPTOR, "ip_porta": ("127.0.0.1", 5002)}, 
       {"id": 3, "role" : TipoNo.ACCEPTOR, "ip_porta": ("127.0.0.1", 5004)}, 
       {"id": 4, "role" : TipoNo.LEARNER, "ip_porta": ("127.0.0.1", 5006)}, 
       {"id": 5, "role" : TipoNo.LEARNER, "ip_porta": ("127.0.0.1", 5008)}]

# Inicializa os nós
n1 = NoP2P(1, TipoNo.ACCEPTOR, "127.0.0.1", 5000, 5001, nos, barrier, 5010)
n2 = NoP2P(2, TipoNo.ACCEPTOR, "127.0.0.1", 5002, 5003, nos, barrier, 5011)
n3 = NoP2P(3, TipoNo.ACCEPTOR, "127.0.0.1", 5004, 5005, nos, barrier, 5012)
n4 = NoP2P(4, TipoNo.LEARNER, "127.0.0.1", 5006, 5007, nos, barrier, 5013)
n5 = NoP2P(5, TipoNo.LEARNER, "127.0.0.1", 5008, 5009, nos, barrier, 5014)

# Inicia os nós
n1.iniciar()
n2.iniciar()
n3.iniciar()
n4.iniciar()
n5.iniciar()
