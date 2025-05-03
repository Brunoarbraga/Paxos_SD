# Arquivo dedicado à implementação do protocolo paxos 
from constants.constants import *
from enum import Enum
import socket
import threading
import time
import json
from itertools import chain
import random
import os

# ---------- CLUSTER SYNC - CLUSTER STORE ----------

# Representa a conexão entre o cluster sync do paxos e o cluter store que manipular o recurso R final
class Sync_Store:
    def __init__(self, host, porta):
        self.host = host  # host do nó do cluster store
        self.porta = porta # porta do nó do cluster store
        self.socket_cSync_cStore = None # socket de comunicação entre os clusters

    # Inicia a conexão entre o Cluster Sync e o Cluster Store
    def iniciar_conexao(self):
        
        if self.socket_cSync_cStore is None:
            self.socket_cSync_cStore = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.socket_cSync_cStore.settimeout(6)
    
        # Se o elemento do store tiver sido derrubada, a conexão não funciona e retorna -1 para ser tratada onde foi chamada
        try:
            sucesso_conexao = self.socket_cSync_cStore.connect_ex((self.host, self.porta))
            return sucesso_conexao
        except Exception as e:
            return -1

    # Envia mensagem do Cluster Sync ao Cluster Store
    def enviar_mensagem(self, mensagem):
        self.socket_cSync_cStore.sendall(json.dumps(mensagem).encode())

    # Cluster Sync espera retorno do Cluster Store
    def esperar_retorno(self):
        dados = self.socket_cSync_cStore.recv(BUFFER_SIZE)
        mensagem = json.loads(dados.decode())
        return mensagem

    # Encerra a conexão entre o Cluster Sync e o Cluster Store
    def finalizar_conexao(self) :
        self.socket_cSync_cStore.close()
        self.socket_cSync_cStore = None


# ---------- CLUSTER STORE ----------

# Envia mensagem para o cluster store propriamente dito
class ClusterStore:
    def __init__(self, lista_endrecos):
        self.cluster_store = [Sync_Store(host, porta) for (host, porta) in lista_endrecos]
    
    # Cluster Store envia mensagem de resposta ao Cluster Sync
    def enviar_mensagem(self, mensagem):
        attempted_indices = set()
        possibilities = [0,1,2]

        # Enquanto não conseguir conectar com o socket do Cluster Store
        # (só vai dar errado se o nó do cluster store tiver caído)
        while True:

            available_indices = [
                i for i in range(len(possibilities)) 
                if i not in attempted_indices
            ] 

            if not available_indices:
                print("\033[41mTODOS OS CLUSTERS FALHARAM! Nenhum cluster disponível.\033[0m")
                os._exit(0)

            selecionado = random.choice(available_indices)
            attempted_indices.add(selecionado) # Mark this one as attempted
            cluster = self.cluster_store[selecionado]

            sucesso = cluster.iniciar_conexao()

            if sucesso != 0:
                print(f"\033[41mO CLUSTER STORE {selecionado} ACESSADO FOI DERRUBADO. TENTANDO OUTRO.\033[0m")
                continue
            else:
                try:
                    cluster.enviar_mensagem(mensagem)
                    resposta = cluster.esperar_retorno()
                    break  # Exit loop on success
                except Exception as e:
                    print(f"\033[41mCLUSTER STORE FOI DERRUBADO COM A REQUISIÇÃO. MANDANDO PARA OUTRO.\033[0m")
                    # Force-retry by continuing the loop (will pick a new cluster)
                    continue
            
        cluster.finalizar_conexao()
        return resposta


# ---------- NÓ DO CLUSTER SYNC ----------

# Nó p2p do cluster sync do protocolo paxos
# recebe requisições dos clientes e realiza o consenso para enviar para o cluster store
class NoP2P:
    def __init__(self, id, role, host, porta_para_nos, porta_para_clientes, vizinhos, barrier):
        self.cluster_store = ClusterStore([("cluster0", 10000), ("cluster1", 10001), ("cluster2", 10002)])
        
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

        # listas para o processo de consenso do learner
        self.commits_recebidos = {}
        self.commits_processados = set()

        # Atributos de transação
        self.barrier = threading.Barrier(barrier) # Barrier para sincronização
        self.preparacao_enviada = False
        self.TID = 1 # Valor de transação único que será utilizado para prometer ou não, incrementa caso não for prometido 
        self.valor = None

        # Preparação
        self.preparacoes_enviadas = 0
        self.respostas_recebidas = 0

        self.mesma_preparacao = 0

        # Promessas
        self.promised_flag = False
        self.promised_value = None
        self.promises_recebidos = 0
        self.promised_end_flag = False

        # Threading
        self.mutex = threading.Event()

        # Socket para escutar conexões
        self.servidor_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

        # Iniciação do servidor
        try:
            self.servidor_socket.bind((self.host, self.porta_para_outros_nos))
        except OSError as e:
            print(f"Erro ao vincular a porta {self.porta_para_outros_nos}: {e}")
        self.servidor_socket.listen()


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
            if self.role == "learner" and vizinho['role'] == "learner": 
                continue
            
            while True:
                try:               
                    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    sock.settimeout(10) # timeout para evitar bloqueio infinito
                    sock.connect(tuple(vizinho['ip_porta']))

                    sock.send(json.dumps({"id": self.id}).encode())

                    if vizinho['role'] == "acceptor":
                        self.sockets_acceptors_clients.append({"id" : vizinho['id'], "socket" : sock, "role": vizinho['role'], "recebeu_prep" : False})
                    else:
                        self.sockets_learners_clients.append({"id" : vizinho['id'], "socket" : sock, "role": vizinho['role'], "recebeu_prep" : False})
                     
                    print(f"Nó {self.id} conectado ao vizinho {vizinho['id']} - {vizinho['role']}")
                    
                    break # se a conexão for bem sucedida, sai do loop
                
                except Exception as e:
                    #print(f"\033[31mErro ao conectar com {vizinho}: {e}. Tentando novamente em 1s...\033[0m")
                    time.sleep(1) # sleep para garantir que o nó vizinho esteja escutando ao tentar conectar

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
                        if vizinho['role'] == "acceptor":
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
        self.cliente_socket.bind(('0.0.0.0', self.porta_para_clientes))
        self.cliente_socket.listen()

        conn, addr = self.cliente_socket.accept()

        # Loop que recebe requisições do cliente
        while True:

            # Recebe requisição de sockets_ativos
            dados = conn.recv(BUFFER_SIZE)

            if not dados:
                break    

            # Converte o json de volta em dicionário
            mensagem = json.loads(dados.decode())

            # Adiciona o TID desse proposer
            mensagem["TID"] = self.TID
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

            # Atualiza o TID da mensagem
            self.TID += 1
            mensagem_json['TID'] = self.TID

            json_string = json.dumps(mensagem_json)
            json_string = json_string.encode()
            
            try:
                # Se tentou mandar a preparação muitas vezes e não deu certo, espera
                self.mandar_preparacao(json.dumps(mensagem_json).encode())  # Converte para JSON e codifica
                self.receber_resposta_preparacao(json.dumps(mensagem_json).encode())  

                # Exponential backoff para tentar evitar contenção infinita
                if(self.mesma_preparacao > 4): #min 1,6s max 8s
                    self.mesma_preparacao = 0
                if(self.mesma_preparacao > 2):
                    time.sleep(random.uniform(0.1, 0.5) * (2 ** self.mesma_preparacao))

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
                    # Se receber um "not promise", incrementa o TID pra tentar de novo
                    else:
                        self.TID = dicionario['TID'] + 1
                        self.mesma_preparacao += 1
                    
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
        if self.promised_flag == False or self.TID < mensagem['TID']:
            self.prometer_preparacao(element, mensagem)
        else:
            self.negar_preparacao(element, mensagem)

    # Devolve um "promise" como resposta à mensagem de preparação de outro nó
    def prometer_preparacao(self, element, mensagem):
        
        self.promised_flag = True
        self.TID = mensagem['TID'] # atualiza o TID com o TID da mensagem maior
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

        mensagem_tupla = ["not promise", mensagem]

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

        # Se a preparação voltou um accept, reseta o contador de mesma preparação
        self.mesma_preparacao = 0

        mensagem['tipo'] = "commit"
 
        json_string = json.dumps(mensagem)
        json_string = json_string.encode()

        for element in self.sockets_learners_servers:
            element['socket'].send(json_string)


    # ---------- ACEITAÇÃO | LADO DO LEARNER ----------
    
    # Verifica se atingiu um consenso das mensagens dos accptors
    def consenso_commit(self, mensagem):
    
        tid = mensagem["TID"]
        timestamp = mensagem["timestamp"]

        if tid not in self.commits_recebidos:
            self.commits_recebidos[tid] = {"timestamp": timestamp, "contagem": 0}

        # Incrementa contagem de commits recebidos para esse TID
        self.commits_recebidos[tid]["contagem"] += 1
        print(f"Learner {self.id} recebeu {self.commits_recebidos[tid]['contagem']} commits para TID {tid}")

        # Verifica se atingiu a maioria para tomar decisão
        if self.commits_recebidos[tid]["contagem"] >= CONSENSO_LEARNERS and tid not in self.commits_processados:
            print(f"\033[32mLearner {self.id} atingiu consenso para TID {tid} com timestamp {timestamp}\033[0m")
            self.commits_processados.add(tid)
            return True
        
        return False

    # Commita (manda pro Cluster Store), recebe a resposta e avisa o cliente
    def commitar(self, mensagem):

        self.valor_aprendido = mensagem['valor'] # aprende o valor
        print(f"\033[36mLearner {self.id} commitando valor {mensagem['valor']} da transação do nó {mensagem['ID']} para o Cluster Store\033[0m")
    
        # Envia mensagem ao Cluster Store
        try:
            resposta = self.cluster_store.enviar_mensagem(mensagem)
            status = resposta.get("status")
        except Exception as e:
            status = "fail"

        # Responde o cliente que mandou a requisição originalmente, falando se a transação deu certo ou não
        self.responder_cliente(mensagem, status)

    # Responde o cliente que mandou a requisição
    def responder_cliente(self, mensagem, success):

        try:
            sock_cliente = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

            print(f"Tentando conectar ao cliente {mensagem['client_host']} na porta {mensagem['client_port']}...")

            sock_cliente.connect((mensagem['client_host'], mensagem["client_port"]))
            print("Conexão com o cliente estabelecida!")

            # Cria a mensagem de aviso
            if success == "success":
                resposta_cliente = {
                    "tipo": "resposta",
                    "status": "Success",
                    "mensagem": "Transação CONFIRMADA pelo Learner.",
                    "TID" : mensagem['TID'],
                    "valor": mensagem['valor']
                }
            
            else:
                resposta_cliente = {
                    "tipo": "resposta",
                    "status": "Fail",
                    "mensagem": "Transação NEGADA. Tente novamente.",
                    "TID" : mensagem['TID'],
                    "valor": mensagem['valor']
                }
            
            # Envia o aviso para o cliente
            print("Enviando resposta ao cliente...")
            sock_cliente.send(json.dumps(resposta_cliente).encode())
            print("\033[32mResposta enviada ao cliente com sucesso!\033[0m")

            # Encerra a conexão
            sock_cliente.close()

        except Exception as e:
            print(f"\033[31mEro ao enviar aviso para o cliente: {e}\033[0m")
            raise
    
    # Recebe uma mensagem de outro nó
    def receber_mensagens(self):
        while True:
            if not self.sockets_acceptors_clients:
                time.sleep(1) # aguarda um pouco antes de tentar novamente
                continue
            
            for element in chain(self.sockets_acceptors_clients, self.sockets_learners_clients):    
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
                            if mensagem["TID"] not in self.commits_recebidos:
                                self.commits_recebidos[mensagem["TID"]] = {"contagem": 0}

                            # if mensagem["TID"] != self.TID:
                            #     print(f"\033[31mLearner {self.id} ignorou commit de TID {mensagem['TID']} (esperado {self.TID})\033[0m")
                            #     continue  # ignora commits antigos

                            # Print detalhado para depuração
                            print(f"\033[33mLearner {self.id} recebeu commit para TID {mensagem['TID']} (esperado {self.TID})\033[0m")

                            # Verifica se atingiu consenso
                            atingiu_consenso = self.consenso_commit(mensagem)

                            if atingiu_consenso:
                                self.commitar(mensagem)

                    except socket.timeout:
                        print(f"\033[33mAviso: Timeout ao receber mensagem no nó {self.id}.\033[0m")
                    except json.JSONDecodeError:
                        print(f"\033[31mErro: Dados recebidos não são JSON válido.{mensagem}\033[0m")
                    except Exception as e:
                        print(f"\033[31mErro ao receber mensagem: {e}\033[0m\n{mensagem}")


# ---------- MAIN ----------

if __name__ == "__main__":
    import sys

    if len(sys.argv) != 8:
        print("Uso: python3 no.py <id_no> <tipo> <host> <porta_para_nos> <porta_para_cliente> <lista_vizinhos> <barrier>")
        sys.exit(1)

    id = int(sys.argv[1])
    tipo = sys.argv[2]
    host = sys.argv[3]
    porta_para_nos = int(sys.argv[4])  
    porta_para_clientes = int(sys.argv[5])
    nos = json.loads(sys.argv[6])
    barrier = int(sys.argv[7])

    no = NoP2P(id, tipo, host, porta_para_nos, porta_para_clientes, nos, barrier)
    
    no.iniciar()