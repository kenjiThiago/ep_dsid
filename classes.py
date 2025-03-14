import socket

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

    def __encontra_vizinho(self, ip, porta) -> Vizinho | None:
        for vizinho in self.vizinhos:
            if vizinho.ip == ip and vizinho.porta == porta:
                return vizinho

    def __manda_mensagem(self, ip, porta, mensagem) -> bool:
        print(f'    Encaminhando mensagem "{mensagem}" para {ip}:{porta}')

        socket_cliente = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

        try:
            socket_cliente.connect((ip, porta))

            socket_cliente.sendall(mensagem.encode())

            socket_cliente.close()

            return True
        except:
            return False

    def inicia_servidor(self):
        socket_servidor = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

        socket_servidor.bind((self.ip, self.porta))
        socket_servidor.listen(1)


        while True:
            conexao, _ = socket_servidor.accept()

            mensagem = conexao.recv(1024).decode()
            if not mensagem:
                break

            mensagens = mensagem.split(" ")
            tipo_mensagem = mensagens[2]
            ip, porta = mensagens[0].split(":")
            porta = int(porta)

            if tipo_mensagem == "PEER_LIST":
                print(f'\n    Resposta recebida: "{mensagem}"')
            else:
                print(f'\n    Mensagem recebida: "{mensagem}"')

            self.relogio += 1
            print(f"    => Atualizando relogio para {self.relogio}")

            vizinho = self.__encontra_vizinho(ip, porta)
            if not vizinho:
                print(f"    Adicionando novo peer {ip}:{porta} status ONLINE")
                vizinho = Vizinho(ip, porta, "ONLINE")
                self.vizinhos.append(vizinho)
                continue


            match tipo_mensagem:
                case "HELLO":
                    vizinho.status = "ONLINE"
                    print(f"    Atualizando peer {ip}:{porta} status {vizinho.status}")
                case "GET_PEERS":
                    vizinho.status = "ONLINE"
                    print(f"    Atualizando peer {ip}:{porta} status {vizinho.status}")
                    m = f"{self.ip}:{self.porta} {self.relogio} PEER_LIST {len(self.vizinhos) - 1}"
                    for vizinho in self.vizinhos:
                        if vizinho.ip == ip and vizinho.porta == porta:
                            continue
                        m += f" {vizinho.ip}:{vizinho.porta}:{vizinho.status}:0"

                    self.__manda_mensagem(ip, porta, m)
                case "PEER_LIST":
                    numero_vizinhos = mensagens[3]

                    vizinho.status = "ONLINE"
                    print(f"    Atualizando peer {ip}:{porta} status {vizinho.status}")
                    for _ in range(int(numero_vizinhos)):
                        ip_vizinho, porta_vizinho, status_vizinho, _ = mensagens.pop().split(":")

                        vizinho_do_vizinho = self.__encontra_vizinho(ip_vizinho, porta_vizinho)
                        if vizinho_do_vizinho:
                            vizinho_do_vizinho.status = status_vizinho
                            print(f"    Atualizando peer {ip_vizinho}:{porta_vizinho} status {vizinho_do_vizinho.status}")
                            continue

                        print(f"    Adicionando novo peer {ip_vizinho}:{porta_vizinho} status {status_vizinho}")
                        self.vizinhos.append(Vizinho(ip_vizinho, porta_vizinho, status_vizinho))
                case "BYE":
                    vizinho.status = "OFFLINE"
                    print(f"    Atualizando peer {ip}:{porta} status {vizinho.status}")
                case _:
                    print("Formato da mensagem errado")


    def lista_peers(self):
        print('''Lista de peers:
        [0] voltar para o menu anterior''')
        for i, vizinho in enumerate(self.vizinhos):
            print(f"        [{i + 1}] {vizinho.ip}:{vizinho.porta} {vizinho.status}")
        comando = int(input("> "))

        if comando == 0:
            return

        if comando > len(self.vizinhos):
            print("Comando não conhecido")
            return

        vizinho = self.vizinhos[comando - 1]
        self.relogio += 1
        print(vizinho.ip, vizinho.porta)

        mensagem = f"{self.ip}:{self.porta} {self.relogio} HELLO"

        print(f"    => Atualizando relogio para {self.relogio}")

        if (self.__manda_mensagem(vizinho.ip, vizinho.porta, mensagem)):
            vizinho.status = "ONLINE"
            print(f"    Atualizando peer {vizinho.ip}:{vizinho.porta} status {vizinho.status}")
        else:
            vizinho.status = "OFFLINE"
            print(f"    Peer {vizinho.ip}:{vizinho.porta} não está ONLINE")
            print(f"    Atualizando peer {vizinho.ip}:{vizinho.porta} status {vizinho.status}")

    def obter_peers(self):
        for vizinho in self.vizinhos:
            self.relogio += 1
            print(f"    => Atualizando relogio para {self.relogio}")

            mensagem = f"{self.ip}:{self.porta} {self.relogio} GET_PEERS"

            self.__manda_mensagem(vizinho.ip, vizinho.porta, mensagem)

    def sair(self):
        print("Saindo...")

        self.relogio += 1

        print(f"    => Atualizando relogio para {self.relogio}")

        for vizinho in self.vizinhos:
            if (vizinho.status == "OFFLINE"):
                continue

            mensagem = f"{self.ip}:{self.porta} {self.relogio} BYE"
            self.__manda_mensagem(vizinho.ip, vizinho.porta, mensagem)
