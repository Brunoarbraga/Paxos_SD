from enum import Enum
import socket
import threading
import time
import json
from constants import *

# from functools import partial

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
        self.vizinhos = vizinhos # lista de 4 vizinhos (host, porta)
        self.sockets_ativos = [] # lista de conexões ativas
        self.barrier = barrier # barrier para sincronização
        self.porta_cliente = porta_cliente
        self.TID = None
        self.valor = None

        # Cria socket para escutar conexões
        self.servidor_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.servidor_socket.bind((self.host, self.porta_para_outros_nos))
        self.servidor_socket.listen() # até 4 conexões simultâneas

    def preparacao(self, mensagem):
        """ Envia uma mensagem para todos os vizinhos conectados """
        for element in self.sockets_ativos:
            # Impede que a mensagem de preparação seja enviada para um learner
            if element['role'] == TipoNo.LEARNER:
                continue

            # Envia a mensagem codificada
            try:
                element['socket'].send(mensagem)
                print(f"Mensagem enviada: {mensagem}")
            except Exception as e:
                print(f"Erro ao enviar mensagem: {e}")

    def conectar_com_clientes(self):
        """ Conecta-se a um cliente externo """
        self.barrier.wait()
        self.cliente_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.cliente_socket.bind((self.host, self.porta_para_clientes))
        self.cliente_socket.listen()

        conn, addr = self.cliente_socket.accept()
        print(f"Nó {self.id} conectado com o cliente {addr}")

        while True:
            dados = conn.recv(BUFFER_SIZE)
            if not dados:
                break
            mensagem = json.loads(dados.decode())
            timestamp = mensagem.get('timestamp')
            print(f"Nó {self.id} recebeu request do cliente com timestamp {timestamp}")

            self.preparacao(dados)
            conn.sendall(json.dumps({"status": "commited"}).encode())  
    
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
                    sock.settimeout(5) # timeout para evitar bloqueio infinito
                    sock.connect(vizinho['ip_porta'])
                    self.sockets_ativos.append({"socket" : sock, "role": vizinho['role']})
                    print(f"Nó {self.id} conectado ao vizinho {vizinho['id']} - {vizinho['role']}")
                    break # se a conexão for bem sucedida, sai do loop
                
                except Exception as e:
                    print(f"Erro ao conectar com {vizinho}: {e}. Tentando novamente em 2s...")
                    time.sleep(2)

    def aceitar_conexoes_vizinhos(self):
        """ Escuta conexões de 4 outros nós """
        self.barrier.wait()
        # while len(self.sockets_ativos) < 4:
        while True:
            try:
                cliente_socket, addr = self.servidor_socket.accept()
                self.sockets_ativos.append({"socket": cliente_socket, "role": TipoNo.ACCEPTOR})
            except Exception as e:
                print(f"Erro ao aceitar conexão: {e}")
                break

    def iniciar(self):
        """ Inicia o nó: conecta-se aos vizinhos e aceita conexões """
        threading.Thread(target=self.conectar_a_vizinhos).start()
        threading.Thread(target=self.aceitar_conexoes_vizinhos).start()
        if self.id == 1:
            threading.Thread(target=self.conectar_com_clientes).start()

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
