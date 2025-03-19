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
    vizinhos_hash = {}
    diretorio_compartilhado = []
    relogio: int

    def __init__(self, ip, porta, arquivo_vizinhos, diretorio_compartilhado):
        self.ip = ip
        self.porta = porta
        self.relogio = 0

        try:
            arquivo = open(arquivo_vizinhos)

            for vizinho in arquivo:
                ip_vizinho, porta_vizinho = vizinho.strip("\n").split(":")
                porta_vizinho = int(porta_vizinho)

                self.__adiciona_novo_vizinho(ip_vizinho, porta_vizinho, "OFFLINE")
            print()
            arquivo.close()

            for f in os.scandir(diretorio_compartilhado):
                if f.is_file():
                    self.diretorio_compartilhado.append(f.name)
        except OSError as e:
            print(e)
            exit(1)

    def __manda_mensagem(self, ip, porta, conteudo_mensagem) -> bool:
        self.relogio += 1
        print(f"    => Atualizando relogio para {self.relogio}")

        mensagem = f"{self.ip}:{self.porta} {self.relogio} {conteudo_mensagem}"

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
        print(f"Adicionando novo peer {ip}:{porta} status {status}")
        vizinho = Vizinho(ip, porta, status)
        self.vizinhos.append(vizinho)
        self.vizinhos_hash[ip, porta] = vizinho
        return vizinho

    def __atualiza_ou_adiciona_vizinho(self, ip, porta, status):
        if (ip, porta) in self.vizinhos_hash:
            vizinho = self.vizinhos_hash[ip, porta]
            self.__atualiza_status(vizinho, status)
            return

        print("    ", end="")
        vizinho = self.__adiciona_novo_vizinho(ip, porta, status)

    def __processa_mensagem(self, conexao) -> bool:
        mensagem = conexao.recv(1024).decode()

        if not mensagem: return False
        if mensagem == "CLOSE": return True

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
            case "HELLO": self.__atualiza_ou_adiciona_vizinho(ip, porta, "ONLINE")
            case "GET_PEERS":
                self.__atualiza_ou_adiciona_vizinho(ip, porta, "ONLINE")

                m = f"PEER_LIST {len(self.vizinhos) - 1}"
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
            case "BYE": self.__atualiza_ou_adiciona_vizinho(ip, porta, "OFFLINE")
            case _: print("Formato da mensagem errado")
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
        comando = int(input("> "))
        print()

        if comando == 0 or comando > len(self.vizinhos):
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

            bloqueio.clear()
            if (not self.__manda_mensagem(vizinho.ip, vizinho.porta, "GET_PEERS")):
                self.__atualiza_status(vizinho, "OFFLINE")
            bloqueio.wait()

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

        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as socket_cliente:
            while True:
                try:
                    socket_cliente.connect((self.ip, self.porta))

                    socket_cliente.sendall("CLOSE".encode())
                    break
                except OSError as e:
                    print(f"Não foi possível fechar o servidor {e}")
