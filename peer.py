import socket
from typing import List, Tuple
import base64
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
    diretorio_compartilhado: List[Tuple[str, int]]
    diretorio_compartilhado_set: set[str]
    caminho_diretorio_compartilhado: str
    relogio: int
    ls_arquivos_tamanho: int
    ls_arquivos: List[Tuple[str, str]]

    def __init__(self, ip, porta, arquivo_vizinhos, diretorio_compartilhado):
        self.ip = ip
        self.porta = porta
        self.vizinhos = []
        self.vizinhos_hash = {}
        self.diretorio_compartilhado = []
        self.diretorio_compartilhado_set = set()
        self.caminho_diretorio_compartilhado = diretorio_compartilhado
        self.relogio = 0

        try:
            with open(arquivo_vizinhos) as arquivo:
                for vizinho in arquivo:
                    ip_vizinho, porta_vizinho = vizinho.strip("\n").split(":")
                    porta_vizinho = int(porta_vizinho)

                    self.__adiciona_novo_vizinho(ip_vizinho, porta_vizinho, "OFFLINE", 0)

            print()

            for f in os.scandir(diretorio_compartilhado):
                if f.is_file():
                    self.diretorio_compartilhado.append((f.name, f.stat().st_size))
                    self.diretorio_compartilhado_set.add(f.name)
        except OSError as e:
            print(e)
            exit(1)

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

    def __atualiza_ou_adiciona_vizinho_indireto(self, ip, porta, status, relogio):
        if (ip, porta) in self.vizinhos_hash:
            vizinho = self.vizinhos_hash[ip, porta]
            if vizinho.relogio > relogio: return
            self.__atualiza_status(vizinho, status)
            self.__atualiza_relogio_vizinhos(vizinho.ip, vizinho.porta, relogio)
            return

        print("    ", end="")
        self.__adiciona_novo_vizinho(ip, porta, status, relogio)

    def __atualiza_ou_adiciona_vizinho_direto(self, ip, porta, status, relogio):
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

        mensagem += "\n"

        conexao.sendall(mensagem.encode())

    def __processa_resposta(self, resposta):
        resposta = resposta.strip("\n")
        ip_origem, porta_origem, relogio, tipo_mensagem, args = self.__processa_parametros(resposta)

        print(f'    Resposta recebida: "{resposta}"')
        self.__atualiza_relogio(relogio)

        if tipo_mensagem == "PEER_LIST":
            numero_vizinhos = args[0]

            self.__atualiza_ou_adiciona_vizinho_direto(ip_origem, porta_origem, "ONLINE", relogio)

            for _ in range(int(numero_vizinhos)):
                ip_vizinho, porta_vizinho, status_vizinho, relogio = args.pop().split(":")
                relogio = int(relogio)
                porta_vizinho = int(porta_vizinho)

                self.__atualiza_ou_adiciona_vizinho_indireto(ip_vizinho, porta_vizinho, status_vizinho, relogio)
        elif tipo_mensagem == "LS_LIST":
            self.__atualiza_ou_adiciona_vizinho_direto(ip_origem, porta_origem, "ONLINE", relogio)
            numero_arquivos = int(args[0])
            arquivos: List[str] = args[1:]
            self.ls_arquivos_tamanho += numero_arquivos

            for i in range(numero_arquivos):
                self.ls_arquivos.append((arquivos[i], f"{ip_origem}:{porta_origem}"))
        elif tipo_mensagem == "FILE":
            self.__atualiza_ou_adiciona_vizinho_direto(ip_origem, porta_origem, "ONLINE", relogio)
            nome_arquivo = args[0]
            conteudo = base64.b64decode(args[len(args) - 1])

            with open(os.path.join(self.caminho_diretorio_compartilhado, nome_arquivo), "wb") as arquivo:
                arquivo.write(conteudo)
                arquivo.seek(0, 2)
                tamanho = arquivo.tell()
                if nome_arquivo not in self.diretorio_compartilhado_set:
                    self.diretorio_compartilhado.append((nome_arquivo, tamanho))
                    self.diretorio_compartilhado_set.add(nome_arquivo)

            print(f"\nDownload do arquivo {nome_arquivo} finalizado.")

    def __manda_mensagem(self, ip_destino, porta_destino, conteudo_mensagem) -> bool:
        tipo_mensagem = conteudo_mensagem.split(" ")[0]
        if tipo_mensagem != "CLOSE": self.__atualiza_relogio(0)

        mensagem = f"{self.ip}:{self.porta} {self.relogio} {conteudo_mensagem}"

        if tipo_mensagem != "CLOSE": print(f'    Encaminhando mensagem "{mensagem}" para {ip_destino}:{porta_destino}')

        mensagem += "\n"

        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as socket_cliente:
            try:
                socket_cliente.connect((ip_destino, porta_destino))

                socket_cliente.sendall(mensagem.encode())

                if tipo_mensagem == "GET_PEERS" or tipo_mensagem == "LS" or tipo_mensagem == "DL":
                    conteudo: str = ""

                    while True:
                        resposta = socket_cliente.recv(1024).decode()
                        conteudo += resposta
                        if not resposta: break

                    if conteudo: self.__processa_resposta(conteudo)

                return True
            except OSError as e:
                print(f"    [Erro] Falha na conexão {e}")
                return False

    def __processa_mensagem(self, conexao) -> bool:
        mensagem = conexao.recv(1024).decode()
        mensagem = mensagem.strip("\n")

        if not mensagem: return False

        ip_origem, porta_origem, relogio, tipo_mensagem, args = self.__processa_parametros(mensagem)

        if tipo_mensagem == "CLOSE": return True

        print(f'\n    Mensagem recebida: "{mensagem}"')
        self.__atualiza_relogio(relogio)

        if tipo_mensagem == "HELLO": self.__atualiza_ou_adiciona_vizinho_direto(ip_origem, porta_origem, "ONLINE", relogio)
        elif tipo_mensagem == "GET_PEERS":
            self.__atualiza_ou_adiciona_vizinho_direto(ip_origem, porta_origem, "ONLINE", relogio)

            resposta = f"PEER_LIST {len(self.vizinhos) - 1}"
            for vizinho in self.vizinhos:
                if vizinho.ip == ip_origem and vizinho.porta == porta_origem:
                    continue
                resposta += f" {vizinho.ip}:{vizinho.porta}:{vizinho.status}:{vizinho.relogio}"

            self.__manda_resposta(conexao, ip_origem, porta_origem, resposta)
        elif tipo_mensagem == "LS":
            self.__atualiza_ou_adiciona_vizinho_direto(ip_origem, porta_origem, "ONLINE", relogio)
            resposta = f"LS_LIST {len(self.diretorio_compartilhado)}"

            for arquivos in self.diretorio_compartilhado:
                resposta += f" {arquivos[0]}:{arquivos[1]}"

            self.__manda_resposta(conexao, ip_origem, porta_origem, resposta)

        elif tipo_mensagem == "DL":
            self.__atualiza_ou_adiciona_vizinho_direto(ip_origem, porta_origem, "ONLINE", relogio)
            nome_arquivo = args[0]

            with open(os.path.join(self.caminho_diretorio_compartilhado, nome_arquivo), "rb") as arquivo:
                conteudo_bytes = arquivo.read()
                conteudo_str = base64.b64encode(conteudo_bytes).decode("utf-8")
                self.__manda_resposta(conexao, ip_origem, porta_origem, f"FILE {nome_arquivo} 0 0 {conteudo_str}")

        elif tipo_mensagem == "BYE": self.__atualiza_ou_adiciona_vizinho_direto(ip_origem, porta_origem, "OFFLINE", relogio)
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
            print(arquivo[0])

        print()

    def busca_arquivos(self):
        self.ls_arquivos_tamanho = 0
        self.ls_arquivos = []
        for vizinho in self.vizinhos:
            if (vizinho.status == "OFFLINE"): continue

            if (not self.__manda_mensagem(vizinho.ip, vizinho.porta, "LS")):
                self.__atualiza_status(vizinho, "OFFLINE")

        print("\nArquivos encontrados na rede:")
        print(f"    {'':<5} {'Nome':<20} | {'Tamanho':<10} | {'Peer'}")
        print(f"    [{' 0':2}] {'<Cancelar>':<21} | {'':<10} | ")

        for i in range(self.ls_arquivos_tamanho):
            nome, tamanho = self.ls_arquivos[i][0].split(":")
            ip_origem, porta_origem = self.ls_arquivos[i][1].split(":")
            porta_origem = int(porta_origem)
            print(f"    [{i + 1:2}] {nome:<21} | {tamanho:<10} | {ip_origem}:{porta_origem}")

        comando = int(input('''\nDigite o numero do arquivo para fazer o download:
> '''))
        if comando > self.ls_arquivos_tamanho or comando == 0: return

        arquivo_escolhido, tamanho = self.ls_arquivos[comando - 1][0].split(":")
        ip_destino, porta_destino = self.ls_arquivos[comando - 1][1].split(":")
        porta_destino = int(porta_destino)
        print(f"arquivo escolhido {arquivo_escolhido}\n")

        self.__manda_mensagem(ip_destino, porta_destino, f"DL {arquivo_escolhido} 0 0")

        print()

    def sair(self):
        print("Saindo...")

        for vizinho in self.vizinhos:
            if (vizinho.status == "OFFLINE"): continue

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
                self.busca_arquivos()
            elif comando == "5":
                print("[TODO] Implementar exibição de estatísticas\n")
            elif comando == "6":
                print("[TODO] Implementar alteração de tamanho de chunk\n")
            elif comando == "9":
                self.sair()
                break
            else:
                print("Comando não conhecido\n")
