# Arquivo dedicado ao comportamento do cluster store e suas tolerâncias à falhas
from constants.constants import *
import socket
import threading
import time
import json
import os


# Definição dos nós do Cluster Store
class noClusterStore:
    def __init__(self, id, host, portaRequisicao, porta1 = None, porta2 = None, porta_no_primario = None, host_no_primario = None, cair = None):
        self.id = id
        self.host = host
        self.portaRequisicao = portaRequisicao # porta para receber requisições do cluster sync
        self.primario = True if id == 0 else False # define se é um nó primário do cluster store ou um nó de backup
        self.cair = cair # flag para simular queda do nó
        self.recurso = []

        if self.primario:
            # Se está conectado ou não com os nós de backup
            self.backup1_conectado = False
            self.backup2_conectado = False
            # Portas de conexão com os nós de backup do Cluster Store
            self.porta1 = porta1
            self.porta2 = porta2
            # Conexão com os nós de backup
            self.conn_backup1 = None
            self.conn_backup2 = None
            # Comunicação com os nós de backup
            self.no_backup1_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.no_backup2_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

        else:
            self.primario_conectado = None
            self.porta_no_primario = porta_no_primario # porta para estabelecer conexão com o nó primário
            self.host_no_primario = host_no_primario # host do nó primário para estabelecer conexão com ele
            self.no_primario_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM) # comunicação com o nó primário

        # Comunicação com o Cluster Sync
        self.no_clusterSync_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

        # Controle de concorrência
        self.mutex = threading.Lock() # trava para garantir acesso seguro ao recurso
        self.esperar_resposta = threading.Condition() # sincronização das threads

    
    # ---------- CONEXÃO DE NÓS ----------

    # Conecta os nós do Cluster Store
    def estabeleceConexoesDoCluster(self):
        if self.primario:
            # Cria as threads para aceitar as conexões dos nós de backup
            conexaoPrimarioBackup1 = threading.Thread(target=self.noPrimarioConexaoBackup1, daemon=True)
            conexaoPrimarioBackup2 = threading.Thread(target=self.noPrimarioConexaoBackup2, daemon=True)
            # Inicia as threads
            conexaoPrimarioBackup1.start()
            conexaoPrimarioBackup2.start()
            # Espera a thread terminar
            conexaoPrimarioBackup1.join()
            conexaoPrimarioBackup2.join()

            # Derruba o nó primário se a flag for passada como parâmetro no compose
            if(self.cair == 3):
                self.derrubar_no()
            
        else:
            time.sleep(1) # delay para garantir que o nó primário está pronto
            
            # Conecta ao nó primário
            sucesso_conexao = self.no_primario_socket.connect_ex((self.host_no_primario, self.porta_no_primario))
            
            # Verifica se a conexão foi realizada
            if sucesso_conexao == 0:
                self.primario_conectado = True

    # Nó primário estabelecendo conexão com o primeiro nó de backup
    def noPrimarioConexaoBackup1(self):
        self.no_backup1_socket.bind((self.host, self.porta1))
        self.no_backup1_socket.listen()
        self.conn_backup1, _ = self.no_backup1_socket.accept()
        self.backup1_conectado = True # Accept gera erro se não funcionar, então não precisa de verificação

    # Nó primário estabelecendo conexão com o segundo nó de backup
    def noPrimarioConexaoBackup2(self):
        self.no_backup2_socket.bind((self.host, self.porta2))
        self.no_backup2_socket.listen()
        self.conn_backup2, _ = self.no_backup2_socket.accept()
        self.backup2_conectado = True # Accept gera erro se não funcionar, então não precisa de verificação


    # ---------- CONEXÃO INTERNA DO CLUSTER ----------

    # Executando o Cluster Store em uma thread separada
    def escutaClusterSync(self):
        # Associa e escuta o socket
        self.no_clusterSync_socket.bind((self.host, self.portaRequisicao))
        self.no_clusterSync_socket.listen()
        
        # Derruba o nó backup sem requisição do cliente
        if self.cair == 1:
            self.derrubar_no()

        while True:    
            conn, addr = self.no_clusterSync_socket.accept()
        
            with conn:
                with self.mutex:
                    self.clienteConectado = True
                    print(f"\033[33mCluster Store ID = {self.id} conectado com o elemento {addr} do cluster sync.\033[0m")
        
                # Recebe e decodifica os dados
                dados = conn.recv(BUFFER_SIZE)
                mensagem = json.loads(dados.decode())
                
                # Inicia o recurso
                self.recurso
                
                # Escreve no recurso
                if self.primario:
                    self.noPrimarioExecutandoRequisicao(mensagem)
                # Envia a requisição de escrita para o nó primário
                else:
                    
                    # Derruba nó primário COM requisição do cliente, antes dele conseguir repassar para o primário
                    if self.cair == 2:
                        self.derrubar_no()

                    self.no_primario_socket.sendall(json.dumps(mensagem).encode())

                    with self.esperar_resposta:
                        self.esperar_resposta.wait()

                # Retorna ao elemento do Cluster Sync um reconhecimento de que a escrita foi concluída
                print("\033[32m Enviando confirmação ao Cluster Sync\033[0m")
                conn.sendall(json.dumps({"status": "success"}).encode())

    # Escuta os demais nós
    def escutaClusterStore(self):
        # Caso seja um nó primário, escuta os nós backup para receber uma requisição repassada por eles
        if self.primario:
            atualizacao_1 = threading.Thread(target=self.noEsperandoRequisicaoAtualizacao, args=(self.conn_backup1,), daemon=True)
            atualizacao_2 = threading.Thread(target=self.noEsperandoRequisicaoAtualizacao, args=(self.conn_backup2,), daemon=True)

            atualizacao_1.start()
            atualizacao_2.start()

            atualizacao_1.join()
            atualizacao_2.join()

        # Caso seja um nó backup, escuta o nó primário para receber uma atualização vinda dele
        else:
            self.noEsperandoRequisicaoAtualizacao(self.no_primario_socket)


    # ---------- ATUALIZAÇÃO ----------

    # Nó recebe requisição/atualizaçã
    def noEsperandoRequisicaoAtualizacao(self, connection):
        while True:
            dados = connection.recv(BUFFER_SIZE)

            if dados:
                try:
                    mensagem = json.loads(dados.decode())
                except:
                    pass

                # Nó primário recebe requisição repassada por um nó de backup
                if self.primario: 
                    self.noPrimarioExecutandoRequisicao(mensagem)
                # Nó backup recebe atualizaçã vinda do nó primário
                else:
                    self.noBackupExecutandoAtualizacao(mensagem)

    # Nó primário executa a requisição e envia a atualização aos nós de backup
    def noPrimarioExecutandoRequisicao(self, mensagem):
        if(not "atualização concluída" in mensagem):
            # Executa a requisição de escrita
            self.recurso.append(mensagem) 
            self.exibir_recurso()
        
            # Manda a atualização para os nós de backup
            # Recebe o retorno de reconhecimento da atualização dos nós de backup
            
            if self.backup1_conectado:
                try:
                    self.conn_backup1.sendall(json.dumps(self.recurso).encode())
                except:
                    self.backup1_conectado = False
            else:
                print("\033[31mNó de backup 1 inacessível. Ignorando-o.\033[0m")
                    
            if no.backup2_conectado:    
                try:
                    self.conn_backup2.sendall(json.dumps(self.recurso).encode())
                except:
                    self.backup2_conectado = False
            else:
                print("\033[31mNó de backup 2 inacessível. Ignorando-o.\033[0m")

        else:
            print("\033[36mAtualização realizada no backup\033[0m")

    # Recurso atuliza e retorna a confimação de atualização ao nó primário
    def noBackupExecutandoAtualizacao(self, atualizacao):
        # Recebe do nó primário a atualizaação a ser feita
        self.recurso.append(atualizacao)

        # Retorna ao nó primário um reconhecimento da atualização
        self.no_primario_socket.sendall(json.dumps("atualização concluída").encode())

        with self.esperar_resposta:
            self.esperar_resposta.notify()


    # ---------- EXECUTA/DERRUBA NÓ ----------

    # Método principal para executar nó
    def executar_no(self):
        self.estabeleceConexoesDoCluster()
        threading.Thread(target=self.escutaClusterSync, daemon=True).start()
        self.escutaClusterStore()

    # Derruba nó para testar o comportamento da conexão Cluster Sync - Cluster Store
    def derrubar_no(self):
        """
        Cair 1: Derruba o nó backup sem requisição do cliente
        Cair 2: Derruba o nó backup com requisição do cliente
        Cair 3: Derruba o nó primário
        """

        # Simula falha de conexão com os nós de backup
        if self.primario:
            self.no_backup1_socket.close() 
            self.no_backup2_socket.close()
        
        # Simula falha de conexão com o nó primário
        else:
            self.no_primario_socket.close()

        self.no_clusterSync_socket.close()

        print(f"\033[31mNó {self.id} sendo derrubado\033[0m")
        os._exit(0)


    # ---------- RECURSO ----------

    def exibir_recurso(self):
        print("\033[36mNova mensagem commitada. Recurso R atualizado:\033[0m")
        for index, messages in enumerate(self.recurso):
            print(f"Mensagem {index}:\n\t{messages}")


# ---------- MAIN ----------

if __name__ == "__main__":
    import sys

    if len(sys.argv) != 6 and len(sys.argv) != 7 and len(sys.argv) != 8 and len(sys.argv) != 9:
        print("Uso: python3 noClusterStore.py <id_no> <host> <porta_para_requisicao_do_cluster_sync> <porta_para_conexao_backup1> <porta_para_conexao_backup2>"
              +"\nou\n"+
              "Uso: python3 noClusterStore.py <id_no> <host> <porta_para_requisicao_do_cluster_sync> 0 0 <porta_do_no_primario> <host_do_no_primario>")
        sys.exit(1)

    id_no = int(sys.argv[1])
    host = sys.argv[2]
    porta_requisicao = int(sys.argv[3]) # porta para requisição do cluster sync

    if id_no == 0:
        porta1 = int(sys.argv[4]) # porta para conexão do primeiro nó de backup
        porta2 = int(sys.argv[5]) # porta para conexão do segundo nó de backup
        cair =  int(sys.argv[6]) if len(sys.argv) == 7 else -1 

        no = noClusterStore(id_no, host, porta_requisicao, porta1, porta2, cair)
    
    else:
        porta_no_primario = int(sys.argv[6]) # porta do nó primário
        host_no_primario = sys.argv[7] # host do nó primário
        
        cair = int(sys.argv[8]) if len(sys.argv) == 9 else -1

        no = noClusterStore(id_no, host, porta_requisicao, None, None, porta_no_primario, host_no_primario, cair)

    # Executa o loop principal do nó
    no.executar_no()

    # cair = 1 - nó sem requisição do cliente
    # cair = 2 - nó com requisição do cliente
    # cair = 3 - nó primário