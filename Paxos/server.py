from enum import Enum
import socket
import threading
import time
import json
from pymongo.mongo_client import MongoClient
from pymongo.server_api import ServerApi

# Link para o Mongo
uri = "mongodb+srv://brunoab:Yukahagany1!@cluster0.r8nnr.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0"

from constants import *

# Define o tipo do nó
class TipoNo (Enum):
    # Todo nó é naturalmente um PROPOSER
    ACCEPTOR = 1
    LEARNER = 2
    CLIENTE = 3

# Nó com conexão par a par
class NoP2P:
    def __init__(self, id, role, host, porta_para_nos, porta_para_clientes, vizinhos, barrier, max_tentativas=5, intervalo_tentativas=1):
        
        """
        host: endereço IP do nó atual.
        porta: porta do nó atual.
        vizinhos: lista (host, porta) dos 4 nós vizinhos.
        """
        
        # Atributos básicos do nó
        self.id = id
        self.role = role # TipoNo
        self.host = host
        self.porta_para_outros_nos = porta_para_nos
        self.porta_para_clientes = porta_para_clientes
        self.vizinhos = vizinhos # Lista de 4 vizinhos (host, porta)

        # Acceptors e learners
        self.sockets_acceptors_clients = [] 
        self.sockets_learners_clients = [] 
        self.sockets_acceptors_servers = []
        self.sockets_learners_servers = [] 

        # Listas para o processo de consenso do learner
        self.commits_recebidos = {}
        self.commits_processados = set()

        # Atributos de transação
        self.barrier = barrier # Barrier para sincronização
        self.preparacao_enviada = False
        self.valor = None

        # Flags de controle
        self.ocupado = False
        self.maior_TID = 1
        self.controle_commit = 1

        # Preparação
        self.preparacoes_enviadas = 0
        self.respostas_recebidas = 0

        # Promessas
        self.promised_flag = False
        self.promised_value = None
        self.promises_recebidos = 0
        self.promised_end_flag = False

        # Threading
        self.mutex = threading.Event()

        # Socket para escutar conexões
        self.servidor_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

        #testeee
        # Variável para controlar o proposer ativo
        self.proposer_ativo = None  # Nenhum proposer ativo no começo
        self.proposer_lock = threading.Lock()  # Lock para controlar acesso a essa variável
        
        # Parâmetros para controle de tentativas
        self.max_tentativas = max_tentativas
        self.intervalo_tentativas = intervalo_tentativas
        #acaba aqui o teste

        # Iniciação do servidor
        try:
            self.servidor_socket.bind((self.host, self.porta_para_outros_nos))
        except OSError as e:
            print(f"Erro ao vincular a porta {self.porta_para_outros_nos}: {e}")
        self.servidor_socket.listen() # até 4 conexões simultâneas


    # ---------- INICIAÇÃO E CONEXÃO DE NÓS ----------

    # Inicia um nó
    def iniciar(self):
        # Conecta aos vizinhos
        threading.Thread(target=self.conectar_a_vizinhos).start()
        threading.Thread(target=self.aceitar_conexoes_vizinhos).start()
        # Conecta ao cliente
        threading.Thread(target=self.conectar_com_clientes).start()
        threading.Thread(target=self.receber_mensagens).start()

    # Conecta um nó a um vizinho usando sockets clientes
    def conectar_a_vizinhos(self):
        self.barrier.wait()
        
        for vizinho in self.vizinhos:
            # Impede que um nó se conecte a ele mesmo
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

                    if vizinho['role'] == TipoNo.ACCEPTOR:
                        self.sockets_acceptors_clients.append({"id" : vizinho['id'], "socket" : sock, "role": vizinho['role'], "recebeu_prep" : False})
                    else:
                        self.sockets_learners_clients.append({"id" : vizinho['id'], "socket" : sock, "role": vizinho['role'], "recebeu_prep" : False})
                     
                    print(f"Nó {self.id} conectado ao vizinho {vizinho['id']} - {vizinho['role']}")
                    
                    break # se a conexão for bem sucedida, sai do loop
                
                except Exception as e:
                    print(f"\033[31mErro ao conectar com {vizinho}: {e}. Tentando novamente em 2s...\033[0m")
                    time.sleep(2)

    # Escuta e aceita conexões de nós vizinhos
    def aceitar_conexoes_vizinhos(self):
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
                        if vizinho['role'] == TipoNo.ACCEPTOR:
                            # Adiciona o socket e o papel do vizinho à lista de envio
                            self.sockets_acceptors_servers.append({
                                "id": vizinho['id'],
                                "socket": cliente_socket,
                                "role": vizinho['role']
                            })
                        else:
                            # Adiciona o socket e o papel do vizinho à lista de envio
                            self.sockets_learners_servers.append({
                                "id": vizinho['id'],
                                "socket": cliente_socket,
                                "role": vizinho['role']
                            })
            
            except Exception as e:
                print(f"\033[31mErro ao aceitar conexão: {e}\033[0m")
                break

    # Conecta um nó a um cliente externo
    def conectar_com_clientes(self):
        self.barrier.wait()
        
        self.cliente_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.cliente_socket.bind((self.host, self.porta_para_clientes))
        self.cliente_socket.listen()

        conn, addr = self.cliente_socket.accept()
        print(f"Conexão estabelecida com o cliente: {addr}")  # <-- Adiciona debug
        
        print(f"Nó {self.id} conectado com o cliente {addr}")

        # Loop que recebe requisições do cliente
        while True:

            # Recebe requisição de sockets_ativos
            dados = conn.recv(BUFFER_SIZE)

            if not dados:
                break    

            # Converte o json de volta em dicionário
            mensagem = json.loads(dados.decode())

            # Adiciona o TID desse proposer
            mensagem["ID"] = self.id

            timestamp = mensagem.get('timestamp')
            print(f"\033[33mNó {self.id} recebeu request do cliente com timestamp {timestamp}\033[0m")

            # Converte de novo para json para mandar na preparação
            json_string = json.dumps(mensagem)
            json_string = json_string.encode()

            self.preparacao(json_string)
    

    # ---------- PREPARAÇÃO | LADO DO PROPOSER ----------

    # Prepara
    def preparacao(self, mensagem):
        
        while self.promised_end_flag == False:

            self.promises_recebidos = 0
            self.preparacoes_enviadas = 0
            self.respostas_recebidas = 0

            # Tenta decodificar a mensagem
            try:
                mensagem_decodificada = mensagem.decode()
                mensagem_json = json.loads(mensagem_decodificada)
            except Exception as e:
                print(f"\033[31mErro ao decodificar mensagem: {e}\033[0m")
                return

            json_string = json.dumps(mensagem_json)
            json_string = json_string.encode()
            
            try:
                self.mandar_preparacao(json.dumps(mensagem_json).encode())  # Converte para JSON e codifica
                self.receber_resposta_preparacao(json.dumps(mensagem_json).encode())  
            except Exception as e:
                print(f"\033[31mErro ao mandar ou receber preparação: {e}\033[0m")

            if self.promises_recebidos >= CONSENSO_ACCEPTERS:
                print(f"\033[32mNó {self.id} chegou a um consenso. Mandando accepts\033[0m")
                self.promised_end_flag = True
        
        self.promised_end_flag = False
        # Garante o formato correto da mensagem antes de enviar
        if isinstance(mensagem, bytes):
            self.mandar_accept(json_string)
        else:
            print(f"\033[31mErro: formato inválido de mensagem para mandar_accept: {mensagem}\033[0m")



    # # Função que tenta fazer um proposer enviar uma preparação --- FUNÇÃO TESTE
    # def enviar_preparacao(self, mensagem):
    #     tentativas = 0
        
    #     while tentativas < self.max_tentativas:
    #         with self.proposer_lock:  # Garante que a operação seja atômica
    #             if self.proposer_ativo is None:
    #                 # Marca esse nó como o proposer ativo
    #                 self.proposer_ativo = self.id
                    
    #                 print(f"Nó {self.id} é o proposer ativo. Enviando preparação...")
                    
    #                 # Envia a mensagem de preparação
    #                 self.mandar_preparacao(mensagem)
                    
    #                 # Após o envio, libera o lock (outros proposers poderão agir)
    #                 self.proposer_ativo = None
    #                 return  # Envio bem-sucedido, sai da função
    #             else:
    #                 print(f"Nó {self.id} não pode enviar preparação porque o nó {self.proposer_ativo} já está enviando uma solicitação.")
            
    #         # Se não conseguiu enviar, espera um intervalo e tenta novamente
    #         tentativas += 1
    #         print(f"Tentativa {tentativas}/{self.max_tentativas} falhou. Tentando novamente em {self.intervalo_tentativas} segundos...")
    #         time.sleep(self.intervalo_tentativas)
        
    #     # Caso o número máximo de tentativas seja atingido
    #     print(f"Nó {self.id} falhou ao tentar enviar a preparação após {self.max_tentativas} tentativas.")



    # Envia uma mensagem de preparação para todos os vizinhos conectados
    def mandar_preparacao(self, mensagem):

        for element in self.sockets_acceptors_servers:
            # Envia a mensagem codificada
            try:
                # Muda o tipo da mensagem
                mensagem_decodificada = mensagem.decode()
                mensagem_json = json.loads(mensagem_decodificada)
                mensagem_json['tipo'] = "preparacao"

                print(f"Nó {self.id} enviando preparação: {mensagem_json}")

                json_string = json.dumps(mensagem_json)
                json_string = json_string.encode()

                element['socket'].send(json_string)
                self.preparacoes_enviadas = self.preparacoes_enviadas + 1

            except Exception as e:
                print(f"\033[31mErro ao enviar preparação: {e}\033[0m")

    # Aguarda as respostas das preparações que mandou
    def receber_resposta_preparacao(self, mensagem):
        
        while self.respostas_recebidas != self.preparacoes_enviadas:
            for element in self.sockets_acceptors_servers:
                try:
                    tupla_de_resposta = element['socket'].recv(BUFFER_SIZE)

                    if not tupla_de_resposta:
                        continue

                    tupla_de_resposta = json.loads(tupla_de_resposta.decode())
                    dicionario = tupla_de_resposta[1]

                    # Se receber um "promise", incrementa os promises recebidos
                    if tupla_de_resposta[0] == "promise":
                        print(f"\033[32mNó {self.id} recebeu 'promise' de preparação do nó: {element['id']}\033[0m")
                        self.promises_recebidos += 1
                    
                    self.respostas_recebidas += 1

                    if self.respostas_recebidas == self.preparacoes_enviadas:
                        break
                
                except Exception as e:
                    print(f"\033[31mErro ao receber resposta de preparação: {e}\033[0m")


    # ---------- PREPARAÇÃO | LADO DO ACCEPTOR ----------

    # Recebe uma mensagem de preparação de outro nó
    def processar_preparacao(self, element, mensagem):

        print(f"\033[33mNó {self.id} recebeu preparação: {mensagem}\033[0m")

        # Se não tiver prometido nenhum valor ainda, promete esse
        if self.promised_flag == False or self.ocupado == False:
            self.ocupado = True
            self.prometer_preparacao(element, mensagem)
        else:
            self.negar_preparacao(element, mensagem)

    # Devolve um "promise" como resposta à mensagem de preparação de outro nó
    def prometer_preparacao(self, element, mensagem):
        
        self.promised_flag = True
        print(f"\033[32mNó {self.id} prometeu preparação: {mensagem}\033[0m")
        
        mensagem_tupla = ["promise", mensagem] #aqui

        # Manda de volta a mensagem com um "promise"
        try:
            element['socket'].send((json.dumps(mensagem_tupla)).encode()) #aqui
        except Exception as e:
            print(f"\033[31mErro ao enviar 'promise': {e}\033[0m")
    
    # Devolve um "not promise" como resposta à mensagem de preparação de outro nó
    def negar_preparacao(self, element, mensagem):

        print(f"\033[31mNó {self.id} negou preparação: {mensagem}\033[0m")

        mensagem_tupla = (("not promise", mensagem))

        # Manda de volta a mensagem com um "not promise" 
        try:
            element['socket'].send((json.dumps(mensagem_tupla)).encode())
        except Exception as e:
            print(f"\033[31mErro ao enviar 'not promise': {e}\033[0m")


    # ---------- ACEITAÇÃO | LADO DO ACCEPTOR ----------

    # Manda um "accept"
    def mandar_accept(self, mensagem):
        
        self.mutex.set()

        # Muda o tipo da mensagem 
        mensagem_decodificada = mensagem.decode()
        mensagem_json = json.loads(mensagem_decodificada)
        mensagem_json['tipo'] = "accept"
        
        json_string = json.dumps(mensagem_json)
        json_string = json_string.encode()
        
        for element in self.sockets_acceptors_servers:
            try:
                element['socket'].send(json_string)
                print(f"\033[32mNó {self.id} enviou 'accept' para {element['id']}\033[0m")
            except Exception as e:
                print(f"\033[31mErro ao enviar 'accept': {e}\033[0m")
    
    # Recebe um "accept"
    def processar_accept(self, mensagem):

        print(f"\033[32mNó {self.id} recebeu 'accept' de: {mensagem['ID']}. Mandando para o learner\033[0m")

        mensagem['tipo'] = "commit"
 
        json_string = json.dumps(mensagem)
        json_string = json_string.encode()

        for element in self.sockets_learners_servers:
            element['socket'].send(json_string)

        self.ocupado = False


    # ---------- ACEITAÇÃO | LADO DO LEARNER ----------
    
    # Verifica se atingiu um consenso das mensagens dos accptors
    def consenso_commit(self, mensagem):

        if self.controle_commit % 2 != 0:
            mensagem['TID'] = self.maior_TID

        tid = mensagem["TID"] 
        timestamp = mensagem["timestamp"]

        if tid not in self.commits_recebidos:
            self.commits_recebidos[tid] = {"timestamp": timestamp, "contagem": 0}

        # Incrementa contagem de commits recebidos para esse TID
        self.commits_recebidos[tid]["contagem"] += 1

        self.controle_commit += 1
        # Verifica se atingiu a maioria para tomar decisão
        if self.commits_recebidos[tid]["contagem"] >= CONSENSO_LEARNERS and tid not in self.commits_processados and self.controle_commit % 2 == 0:
            print(f"----------consenso com tid {tid}")
            self.commits_processados.add(tid)
            self.maior_TID += 1
            return True
        
        print(f"\033[31mLearner {self.id} ainda NÃO atingiu consenso para TID {tid}\033[0m")
        
        # Chamando a função enviar_preparacao
        # if tid not in self.commits_processados:
        #     print(f"Nó {self.id} ainda não processou o TID {tid}. Enviando preparação...")
        #     mensagem_de_preparacao = {"TID": tid, "timestamp": timestamp}
        #     self.enviar_preparacao(mensagem_de_preparacao)
            
        return False

    # Commita e avisa o cliente
    def commitar(self, mensagem):
        self.valor_aprendido = mensagem['valor'] # aprende o valor
        print(f"\033[32mLearner {self.id} commitando valor {mensagem['valor']} da transação TID = {mensagem['TID']}\033[0m")

        mensagem['TID'] = self.maior_TID

        # Conecta ao servidor Mongo
        client = MongoClient(uri, server_api=ServerApi('1'))
        # Escolhe o banco de dados
        db = client["client" + mensagem['client_id']]
        # Escolne uma coleção (só tem uma)
        colecao = db["transactions"]
        # Insere na coleção
        colecao.insert_one(mensagem)

        # Verifica se a mensagem tem infos do cliente
        if "client_host" not in mensagem or "client_port" not in mensagem:
            print(f"\033[31mErro: client_host ou client_port ausente na mensagem {mensagem}\033[0m")
            return
    
        # Conecta ao cliente
        try:
            sock_cliente = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

            print(f"Tentando conectar ao cliente {mensagem['client_host']} na porta {mensagem['client_port']}...")

            sock_cliente.connect((mensagem['client_host'], mensagem["client_port"]))
            print("Conexão com o cliente estabelecida!")

            # Cria a mensagem de aviso
            resposta_cliente = {
                "tipo": "resposta",
                "status": "sucesso",
                "mensagem": "Transação confirmada pelo Learner",
                "valor": mensagem['valor']
            }
            
            # Envia o aviso para o cliente
            print("Enviando resposta ao cliente...")
            sock_cliente.send(json.dumps(resposta_cliente).encode())

            print("\033[32mResposta enviada com sucesso!\033[0m")

            # Encerra a conexão
            sock_cliente.close()


        except Exception as e:
            print(f"\033[31mErro ao enviar aviso para o cliente: {e}\033[0m")
            raise

    # Recebe uma mensagem de outro nó
    def receber_mensagens(self):
        while True:
            if not self.sockets_acceptors_clients:
                time.sleep(1) # aguarda um pouco antes de tentar novamente
                continue
            
            for element in self.sockets_acceptors_clients:    
                    element['socket'].settimeout(1)

                    try:
                        dados = element['socket'].recv(BUFFER_SIZE)
                        
                        if not dados:
                            continue

                        mensagem = json.loads(dados.decode())

                        if mensagem['tipo'] == "preparacao":
                            self.processar_preparacao(element, mensagem)
                        elif mensagem['tipo'] == "accept":
                            self.processar_accept(mensagem)
                        elif mensagem['tipo'] == "commit":
                         
                            # Verifica se atingiu consenso
                            if self.consenso_commit(mensagem):
                                self.commitar(mensagem)

                    except socket.timeout:
                        print(f"\033[33mAviso: Timeout ao receber mensagem no nó {self.id}.\033[0m")
                    except json.JSONDecodeError:
                        print(f"\033[31mErro: Dados recebidos não são JSON válido.\033[0m")
                    except Exception as e:
                        print(f"\033[31mErro ao receber mensagem: {e}\033[0m\n{mensagem}")


# ---------- ÁREA DE TESTE ----------

barrier = threading.Barrier(3)

# Inicializa o vetor de nós
nos = [{"id": 1, "role" : TipoNo.ACCEPTOR , "ip_porta" : ("127.0.0.1", 5000)},
       {"id": 2, "role" : TipoNo.ACCEPTOR, "ip_porta": ("127.0.0.1", 5002)}, 
       {"id": 3, "role" : TipoNo.ACCEPTOR, "ip_porta": ("127.0.0.1", 5004)}, 
       {"id": 4, "role" : TipoNo.LEARNER, "ip_porta": ("127.0.0.1", 5006)}, 
       {"id": 5, "role" : TipoNo.LEARNER, "ip_porta": ("127.0.0.1", 5008)}]

# Inicializa os nós
n1 = NoP2P(1, TipoNo.ACCEPTOR, "127.0.0.1", 5000, 5001, nos, barrier)
n2 = NoP2P(2, TipoNo.ACCEPTOR, "127.0.0.1", 5002, 5003, nos, barrier)
n3 = NoP2P(3, TipoNo.ACCEPTOR, "127.0.0.1", 5004, 5005, nos, barrier)
n4 = NoP2P(4, TipoNo.LEARNER, "127.0.0.1", 5006, 5007, nos, barrier)
n5 = NoP2P(5, TipoNo.LEARNER, "127.0.0.1", 5008, 5009, nos, barrier)

# Inicia os nós
n1.iniciar()
n2.iniciar()
n3.iniciar()
n4.iniciar()
n5.iniciar()
