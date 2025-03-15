import socket
import threading
import os

bloqueio = threading.Event()

class Vizinho:
    ip: str
    porta: int
    status: str

    def __init__(self, ip, porta, status):
        self.ip = ip
        self.porta = porta
        self.status = status

class Peer:
    ip: str
    porta: int
    vizinhos = []
    diretorio_compartilhado: str
    relogio: int

    def __init__(self, ip, porta, arquivo_vizinhos, diretorio_compartilhado):
        self.ip = ip
        self.porta = porta
        self.diretorio_compartilhado = diretorio_compartilhado
        self.relogio = 0

        arquivo = open(arquivo_vizinhos)

        for vizinho in arquivo:
            ip_vizinho, porta_vizinho = vizinho.strip("\n").split(":")

            novo_vizinho = Vizinho(ip_vizinho, int(porta_vizinho), "OFFLINE")
            self.vizinhos.append(novo_vizinho)

    def __manda_mensagem(self, ip, porta, mensagem) -> bool:
        self.relogio += 1
        print(f"    => Atualizando relogio para {self.relogio}")

        print(f'    Encaminhando mensagem "{mensagem}" para {ip}:{porta}')

        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as socket_cliente:
            try:
                socket_cliente.connect((ip, porta))

                socket_cliente.sendall(mensagem.encode())
                return True
            except:
                bloqueio.set()
                return False

    def __atualiza_status(self, peer, status):
        peer.status = status
        print(f"    Atualizando peer {peer.ip}:{peer.porta} status {peer.status}")

    def __adiciona_novo_vizinho(self, ip, porta, status) -> Vizinho:
        print(f"    Adicionando novo peer {ip}:{porta} status {status}")
        vizinho = Vizinho(ip, porta, status)
        self.vizinhos.append(vizinho)
        return vizinho

    def __atualiza_ou_adiciona_vizinho(self, ip, porta, status):
        for vizinho in self.vizinhos:
            if vizinho.ip == ip and vizinho.porta == porta:
                self.__atualiza_status(vizinho, status)
                return

        vizinho = self.__adiciona_novo_vizinho(ip, porta, status)

    def __processa_mensagem(self, conexao):
        mensagem = conexao.recv(1024).decode()
        if not mensagem:
            return

        mensagens = mensagem.split(" ")
        ip, porta = mensagens[0].split(":")
        porta = int(porta)
        tipo_mensagem = mensagens[2]

        if tipo_mensagem == "PEER_LIST":
            print(f'    Resposta recebida: "{mensagem}"')
        else:
            print(f'\n    Mensagem recebida: "{mensagem}"')

        self.relogio += 1
        print(f"    => Atualizando relogio para {self.relogio}")

        match tipo_mensagem:
            case "HELLO":
                self.__atualiza_ou_adiciona_vizinho(ip, porta, "ONLINE")
            case "GET_PEERS":
                self.__atualiza_ou_adiciona_vizinho(ip, porta, "ONLINE")

                m = f"{self.ip}:{self.porta} {self.relogio} PEER_LIST {len(self.vizinhos) - 1}"
                for vizinho in self.vizinhos:
                    if vizinho.ip == ip and vizinho.porta == porta:
                        continue
                    m += f" {vizinho.ip}:{vizinho.porta}:{vizinho.status}:0"

                self.__manda_mensagem(ip, porta, m)
            case "PEER_LIST":
                numero_vizinhos = mensagens[3]

                self.__atualiza_ou_adiciona_vizinho(ip, porta, "ONLINE")

                for _ in range(int(numero_vizinhos)):
                    ip_vizinho, porta_vizinho, status_vizinho, _ = mensagens.pop().split(":")
                    porta_vizinho = int(porta_vizinho)

                    self.__atualiza_ou_adiciona_vizinho(ip_vizinho, porta_vizinho, status_vizinho)

                bloqueio.set()
            case "BYE":
                self.__atualiza_ou_adiciona_vizinho(ip, porta, "OFFLINE")
            case _:
                print("Formato da mensagem errado")

    def inicia_servidor(self):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as socket_servidor:
            socket_servidor.bind((self.ip, self.porta))
            socket_servidor.listen(1)
            while True:
                conexao, _ = socket_servidor.accept()

                with conexao:
                    self.__processa_mensagem(conexao)


    def lista_peers(self):
        print('''\nLista de peers:
        [0] voltar para o menu anterior''')

        for i, vizinho in enumerate(self.vizinhos):
            print(f"        [{i + 1}] {vizinho.ip}:{vizinho.porta} {vizinho.status}")
        comando = int(input("> "))
        print()

        if comando == 0 or comando > len(self.vizinhos):
            return

        vizinho = self.vizinhos[comando - 1]

        mensagem = f"{self.ip}:{self.porta} {self.relogio} HELLO"

        if (self.__manda_mensagem(vizinho.ip, vizinho.porta, mensagem)):
            self.__atualiza_status(vizinho, "ONLINE")
        else:
            self.__atualiza_status(vizinho, "OFFLINE")

        print()

    def obter_peers(self):
        tamanho = len(self.vizinhos)
        for i in range(tamanho):
            vizinho = self.vizinhos[i]

            mensagem = f"{self.ip}:{self.porta} {self.relogio} GET_PEERS"

            bloqueio.clear()
            if (self.__manda_mensagem(vizinho.ip, vizinho.porta, mensagem)):
                self.__atualiza_status(vizinho, "ONLINE")
            else:
                self.__atualiza_status(vizinho, "OFFLINE")
            bloqueio.wait()
        print()

    def lista_arquivos_locais(self):
        arquivos = []
        for f in os.scandir(self.diretorio_compartilhado):
            if f.is_file():
                arquivos.append(f.name)

        for arquivo in arquivos:
            print(arquivo)

        print()

    def sair(self):
        print("Saindo...")

        for vizinho in self.vizinhos:
            if (vizinho.status == "OFFLINE"):
                continue

            mensagem = f"{self.ip}:{self.porta} {self.relogio} BYE"
            self.__manda_mensagem(vizinho.ip, vizinho.porta, mensagem)
        print()
