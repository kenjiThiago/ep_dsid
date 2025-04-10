import socket
from typing import List, Tuple
import os

class Vizinho:
    ip: str
    porta: int
    status: str
    relogio: int

    def __init__(self, ip, porta, status, relogio):
        self.ip = ip
        self.porta = porta
        self.status = status
        self.relogio = relogio

class Peer:
    ip: str
    porta: int
    vizinhos: List[Vizinho]
    vizinhos_hash: dict[Tuple[str, int], Vizinho]
    diretorio_compartilhado: List[str]
    relogio: int

    def __init__(self, ip, porta, arquivo_vizinhos, diretorio_compartilhado):
        self.ip = ip
        self.porta = porta
        self.relogio = 0
        self.vizinhos = []
        self.vizinhos_hash = {}
        self.diretorio_compartilhado = []

        try:
            with open(arquivo_vizinhos) as arquivo:
                for vizinho in arquivo:
                    ip_vizinho, porta_vizinho = vizinho.strip("\n").split(":")
                    porta_vizinho = int(porta_vizinho)

                    self.__adiciona_novo_vizinho(ip_vizinho, porta_vizinho, "OFFLINE", 0)

            print()

            for f in os.scandir(diretorio_compartilhado):
                if f.is_file():
                    self.diretorio_compartilhado.append(f.name)
        except OSError as e:
            print(e)
            exit(1)

    def __printa_vizinhos(self):
        for vizinho in self.vizinhos:
            print(f"{vizinho.ip}:{vizinho.porta}", vizinho.status, vizinho.relogio)
        print()

    def __atualiza_relogio(self, relogio_vizinho):
        self.relogio = max(self.relogio, relogio_vizinho)
        self.relogio += 1
        print(f"    => Atualizando relogio para {self.relogio}")

    def __atualiza_relogio_vizinhos(self, ip, porta, relogio):
        if (ip, porta) in self.vizinhos_hash:
            vizinho = self.vizinhos_hash[ip, porta]
            vizinho.relogio = max(vizinho.relogio, relogio)

    def __atualiza_status(self, peer, status):
        peer.status = status
        print(f"    Atualizando peer {peer.ip}:{peer.porta} status {peer.status}")

    def __adiciona_novo_vizinho(self, ip, porta, status, relogio):
        print(f"Adicionando novo peer {ip}:{porta} status {status}")
        vizinho = Vizinho(ip, porta, status, relogio)
        self.vizinhos.append(vizinho)
        self.vizinhos_hash[ip, porta] = vizinho

    def __atualiza_ou_adiciona_vizinho(self, ip, porta, status, relogio):
        if (ip, porta) in self.vizinhos_hash:
            vizinho = self.vizinhos_hash[ip, porta]
            self.__atualiza_status(vizinho, status)
            self.__atualiza_relogio_vizinhos(vizinho.ip, vizinho.porta, relogio)
            return

        print("    ", end="")
        self.__adiciona_novo_vizinho(ip, porta, status, relogio)

    def __processa_parametros(self, mensagem) -> Tuple[str, int, int, str, List]:
        parametros = mensagem.split(" ")

        ip, porta = parametros[0].split(":")
        porta = int(porta)
        relogio = int(parametros[1])
        tipo_mensagem = parametros[2]
        args = parametros[3:]

        return ip, porta, relogio, tipo_mensagem, args

    def __manda_resposta(self, conexao, ip_destino, porta_destino, conteudo_mensagem):
        self.__atualiza_relogio(0)

        mensagem = f"{self.ip}:{self.porta} {self.relogio} {conteudo_mensagem}"

        print(f'    Encaminhando resposta "{mensagem}" para {ip_destino}:{porta_destino}')

        conexao.sendall(mensagem.encode())

    def __processa_resposta(self, resposta):
        ip_origem, porta_origem, relogio, tipo_mensagem, args = self.__processa_parametros(resposta)

        print(f'    Resposta recebida: "{resposta}"')
        self.__atualiza_relogio(relogio)

        if tipo_mensagem == "PEER_LIST":
            numero_vizinhos = args[0]

            self.__atualiza_ou_adiciona_vizinho(ip_origem, porta_origem, "ONLINE", relogio)

            for _ in range(int(numero_vizinhos)):
                ip_vizinho, porta_vizinho, status_vizinho, relogio = args.pop().split(":")
                relogio = int(relogio)
                porta_vizinho = int(porta_vizinho)

                self.__atualiza_ou_adiciona_vizinho(ip_vizinho, porta_vizinho, status_vizinho, relogio)

    def __manda_mensagem(self, ip_destino, porta_destino, conteudo_mensagem) -> bool:
        if conteudo_mensagem != "CLOSE": self.__atualiza_relogio(0)

        mensagem = f"{self.ip}:{self.porta} {self.relogio} {conteudo_mensagem}"

        if conteudo_mensagem != "CLOSE": print(f'    Encaminhando mensagem "{mensagem}" para {ip_destino}:{porta_destino}')

        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as socket_cliente:
            try:
                socket_cliente.connect((ip_destino, porta_destino))

                socket_cliente.sendall(mensagem.encode())

                if conteudo_mensagem == "GET_PEERS":
                    resposta = socket_cliente.recv(1024).decode()
                    if resposta: self.__processa_resposta(resposta)

                return True
            except:
                print(f"    [Erro] Falha na conexão")
                return False

    def __processa_mensagem(self, conexao) -> bool:
        mensagem = conexao.recv(1024).decode()

        if not mensagem: return False

        ip_origem, porta_origem, relogio, tipo_mensagem, _ = self.__processa_parametros(mensagem)

        if tipo_mensagem == "CLOSE": return True

        print(f'\n    Mensagem recebida: "{mensagem}"')
        self.__atualiza_relogio(relogio)

        if tipo_mensagem == "HELLO": self.__atualiza_ou_adiciona_vizinho(ip_origem, porta_origem, "ONLINE", relogio)
        elif tipo_mensagem == "GET_PEERS":
            self.__atualiza_ou_adiciona_vizinho(ip_origem, porta_origem, "ONLINE", relogio)

            resposta = f"PEER_LIST {len(self.vizinhos) - 1}"
            for vizinho in self.vizinhos:
                if vizinho.ip == ip_origem and vizinho.porta == porta_origem:
                    continue
                resposta += f" {vizinho.ip}:{vizinho.porta}:{vizinho.status}:{vizinho.relogio}"

            self.__manda_resposta(conexao, ip_origem, porta_origem, resposta)
        elif tipo_mensagem == "BYE": self.__atualiza_ou_adiciona_vizinho(ip_origem, porta_origem, "OFFLINE", relogio)
        else: print("Formato da mensagem errado")

        return False

    def inicia_servidor(self):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as socket_servidor:
            socket_servidor.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            socket_servidor.bind((self.ip, self.porta))
            socket_servidor.listen(1)
            while True:
                conexao, _ = socket_servidor.accept()

                with conexao:
                    if (self.__processa_mensagem(conexao)): break

    def lista_peers(self):
        print('''Lista de peers:
        [0] voltar para o menu anterior''')

        for i, vizinho in enumerate(self.vizinhos):
            print(f"        [{i + 1}] {vizinho.ip}:{vizinho.porta} {vizinho.status}")
        comando = input("> ")
        print()

        tamanho = len(self.vizinhos)

        if not comando.isdigit():
            print(f"O input deve ser um número de 0 a {tamanho}\n")
            return

        comando = int(comando)
        if comando == 0 or comando > tamanho:
            return

        vizinho = self.vizinhos[comando - 1]

        if (self.__manda_mensagem(vizinho.ip, vizinho.porta, "HELLO")):
            self.__atualiza_status(vizinho, "ONLINE")
        else:
            self.__atualiza_status(vizinho, "OFFLINE")

        print()

    def obter_peers(self):
        tamanho = len(self.vizinhos)
        for i in range(tamanho):
            vizinho = self.vizinhos[i]

            if (not self.__manda_mensagem(vizinho.ip, vizinho.porta, "GET_PEERS")):
                self.__atualiza_status(vizinho, "OFFLINE")

        print()

    def lista_arquivos_locais(self):
        for arquivo in self.diretorio_compartilhado:
            print(arquivo)

        print()

    def sair(self):
        print("Saindo...")

        for vizinho in self.vizinhos:
            if (vizinho.status == "OFFLINE"):
                continue

            self.__manda_mensagem(vizinho.ip, vizinho.porta, "BYE")

        if (not self.__manda_mensagem(self.ip, self.porta, "CLOSE")):
            print("[Erro] Falha ao fechar o servidor")

    def inicia_cliente(self):
        while True:
            comando = input('''Escolha um comando:
        [1] Listar peers
        [2] Obter peers
        [3] Listar arquivos locais
        [4] Buscar arquivos
        [5] Exibir estatisticas
        [6] Alterar tamanho de chunk
        [9] Sair
> ''')
            print()

            if comando == "1":
                self.lista_peers()
            elif comando == "2":
                self.obter_peers()
            elif comando == "3":
                self.lista_arquivos_locais()
            elif comando == "4":
                print("[TODO] Implementar busca de arquivos\n")
            elif comando == "5":
                print("[TODO] Implementar exibição de estatísticas\n")
            elif comando == "6":
                print("[TODO] Implementar alteração de tamanho de chunk\n")
            elif comando == "9":
                self.sair()
                break
            elif comando == "10":
                self.__printa_vizinhos()
            else:
                print("Comando não conhecido\n")
