import socket
from typing import List, Tuple
import base64
import os
import math
import threading
import time
import statistics

class Vizinho:

    def __init__(self, ip, porta, status, relogio):
        self.ip: str = ip
        self.porta: int = porta
        self.status: str = status
        self.relogio: int = relogio

class Peer:

    def __init__(self, ip, porta, arquivo_vizinhos, diretorio_compartilhado):
        self.ip: str = ip
        self.porta: int = porta
        self.vizinhos: List[Vizinho] = []
        self.vizinhos_hash: dict[Tuple[str, int], Vizinho] = {}
        self.diretorio_compartilhado: List[Tuple[str, int]] = []
        self.diretorio_compartilhado_set: set[str] = set()
        self.caminho_diretorio_compartilhado: str = diretorio_compartilhado
        self.relogio: int = 0
        self.tamanho_chunk: int = 256
        self.ls_arquivos_tamanho: int = 0
        self.ls_arquivos: List[Tuple[str, str]] = []
        self.ls_arquivos_hash: dict[str, int] = {}
        self.tempo_total_escrita: float = 0.0
        self.estatisticas: dict[Tuple[int, int, int], List[float]] = {}

        self.relogio_lock = threading.Lock()
        self.main_lock = threading.Lock()
        self.file_locks = {}
        self.file_locks_lock = threading.Lock()
        self.tempo_escrita_lock = threading.Lock()

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
        with self.relogio_lock:
            self.relogio = max(self.relogio, relogio_vizinho)
            self.relogio += 1
            relogio = self.relogio
            print(f"    => Atualizando relogio para {relogio}")

    def __atualiza_status(self, peer, status):
        peer.status = status
        print(f"    Atualizando peer {peer.ip}:{peer.porta} status {peer.status}")

    def __adiciona_novo_vizinho(self, ip, porta, status, relogio):
        print(f"Adicionando novo peer {ip}:{porta} status {status}")
        vizinho = Vizinho(ip, porta, status, relogio)
        self.vizinhos.append(vizinho)
        self.vizinhos_hash[ip, porta] = vizinho

    def __atualiza_ou_adiciona_vizinho(self, ip, porta, status, relogio, modo=None):
        with self.main_lock:
            if (ip, porta) in self.vizinhos_hash:
                vizinho = self.vizinhos_hash[ip, porta]
                if vizinho.relogio > relogio and modo == "indireto": return
                self.__atualiza_status(vizinho, status)
                vizinho.relogio = max(vizinho.relogio, relogio)
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

            self.__atualiza_ou_adiciona_vizinho(ip_origem, porta_origem, "ONLINE", relogio)

            for _ in range(int(numero_vizinhos)):
                ip_vizinho, porta_vizinho, status_vizinho, relogio = args.pop().split(":")
                relogio = int(relogio)
                porta_vizinho = int(porta_vizinho)

                self.__atualiza_ou_adiciona_vizinho(ip_vizinho, porta_vizinho, status_vizinho, relogio, "indireto")
        elif tipo_mensagem == "LS_LIST":
            self.__atualiza_ou_adiciona_vizinho(ip_origem, porta_origem, "ONLINE", relogio)
            numero_arquivos = int(args[0])
            arquivos: List[str] = args[1:]

            for i in range(numero_arquivos):
                arquivo = arquivos[i]
                origem = f"{ip_origem}:{porta_origem}"
                if arquivo not in self.ls_arquivos_hash:
                    self.ls_arquivos_hash[arquivo] = self.ls_arquivos_tamanho
                    self.ls_arquivos.append((arquivo, origem))
                    self.ls_arquivos_tamanho += 1
                else:
                    indice = self.ls_arquivos_hash[arquivo]
                    nome, origens_atuais = self.ls_arquivos[indice]
                    nova_origens = origens_atuais + ", " + origem
                    self.ls_arquivos[indice] = (nome, nova_origens)
        elif tipo_mensagem == "FILE":
            self.__atualiza_ou_adiciona_vizinho(ip_origem, porta_origem, "ONLINE", relogio)
            nome_arquivo = args[0]
            chunk = int(args[2])
            conteudo = base64.b64decode(args[3])
            offset = chunk * self.tamanho_chunk

            with self.file_locks_lock:
                if nome_arquivo not in self.file_locks:
                    self.file_locks[nome_arquivo] = threading.Lock()
                file_lock = self.file_locks[nome_arquivo]

            with file_lock:
                caminho_arquivo = os.path.join(self.caminho_diretorio_compartilhado, nome_arquivo)
                modo = "r+b" if os.path.exists(caminho_arquivo) else "wb"

                inicio_escrita = time.perf_counter()
                with open(caminho_arquivo, modo) as arquivo:
                    arquivo.seek(offset)
                    arquivo.write(conteudo)
                    arquivo.seek(0, 2)
                    tamanho = arquivo.tell()
                    with self.main_lock:
                        if nome_arquivo not in self.diretorio_compartilhado_set:
                            self.diretorio_compartilhado.append((nome_arquivo, tamanho))
                            self.diretorio_compartilhado_set.add(nome_arquivo)
                fim_escrita = time.perf_counter()

                with self.tempo_escrita_lock:
                    self.tempo_total_escrita += (fim_escrita - inicio_escrita)


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
            except socket.timeout:
                print(f"Timeout ao conectar com {ip_destino}:{porta_destino}")
                return False
            except ConnectionRefusedError:
                print(f"Conexão recusada por {ip_destino}:{porta_destino}")
                return False
            except Exception as e:
                print(f"Erro inesperado: {e}")
                return False

    def __processa_mensagem(self, conexao) -> bool:
        mensagem = conexao.recv(1024).decode()
        mensagem = mensagem.strip("\n")

        if not mensagem: return False

        ip_origem, porta_origem, relogio, tipo_mensagem, args = self.__processa_parametros(mensagem)

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
        elif tipo_mensagem == "LS":
            self.__atualiza_ou_adiciona_vizinho(ip_origem, porta_origem, "ONLINE", relogio)
            resposta = f"LS_LIST {len(self.diretorio_compartilhado)}"

            for arquivos in self.diretorio_compartilhado:
                resposta += f" {arquivos[0]}:{arquivos[1]}"

            self.__manda_resposta(conexao, ip_origem, porta_origem, resposta)

        elif tipo_mensagem == "DL":
            self.__atualiza_ou_adiciona_vizinho(ip_origem, porta_origem, "ONLINE", relogio)
            nome_arquivo = args[0]
            tamanho_chunk = int(args[1])
            chunk = int(args[2])

            offset = chunk * tamanho_chunk

            with open(os.path.join(self.caminho_diretorio_compartilhado, nome_arquivo), "rb") as arquivo:
                arquivo.seek(offset)
                conteudo_bytes = arquivo.read(tamanho_chunk)
                tamanho_lido = len(conteudo_bytes)
                conteudo_str = base64.b64encode(conteudo_bytes).decode("utf-8")
                self.__manda_resposta(conexao, ip_origem, porta_origem, f"FILE {nome_arquivo} {tamanho_lido} {chunk} {conteudo_str}")

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
            print(f"        [{i + 1}] {vizinho.ip}:{vizinho.porta} {vizinho.status} (clock: {vizinho.relogio})")
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
        self.ls_arquivos_hash = {}
        self.tempo_total_escrita = 0.0
        for vizinho in self.vizinhos:
            if (vizinho.status == "OFFLINE"): continue

            if (not self.__manda_mensagem(vizinho.ip, vizinho.porta, "LS")):
                self.__atualiza_status(vizinho, "OFFLINE")

        print("\nArquivos encontrados na rede:")
        print(f"    {'':<5} {'Nome':<20} | {'Tamanho':<10} | {'Peer'}")
        print(f"    [{' 0':2}] {'<Cancelar>':<21} | {'':<10} | ")

        for i in range(self.ls_arquivos_tamanho):
            nome, tamanho = self.ls_arquivos[i][0].split(":")
            origens = self.ls_arquivos[i][1]
            print(f"    [{i + 1:2}] {nome:<21} | {tamanho:<10} | {origens}")

        comando = int(input('''\nDigite o numero do arquivo para fazer o download:
> '''))
        if comando > self.ls_arquivos_tamanho or comando == 0: return

        arquivo_escolhido, tamanho = self.ls_arquivos[comando - 1][0].split(":")

        destinos = self.ls_arquivos[comando - 1][1].split(", ")
        numero_destinos = len(destinos)
        print(f"arquivo escolhido {arquivo_escolhido}\n")
        tamanho = int(tamanho)

        numero_chunks = math.ceil(tamanho / self.tamanho_chunk)
        indice_chunk = 0
        inicio = time.perf_counter()
        while indice_chunk < numero_chunks:
            thread_mensagens = []

            for _ in range(numero_destinos):
                if indice_chunk >= numero_chunks:
                    break

                ip_destino, porta_destino = destinos[indice_chunk % numero_destinos].split(":")
                porta_destino = int(porta_destino)

                thread_mensagem = threading.Thread(
                    target=self.__manda_mensagem,
                    args=(ip_destino, porta_destino, f"DL {arquivo_escolhido} {self.tamanho_chunk} {indice_chunk}"),
                )
                thread_mensagens.append(thread_mensagem)
                thread_mensagem.start()

                indice_chunk += 1

            for thread_mensagem in thread_mensagens:
                thread_mensagem.join()

        fim = time.perf_counter()

        tempo_total = fim - inicio
        tempo_sem_escrita = tempo_total - self.tempo_total_escrita

        if (self.tamanho_chunk, numero_destinos, tamanho) not in self.estatisticas:
            self.estatisticas[(self.tamanho_chunk, numero_destinos, tamanho)] = [tempo_sem_escrita]
        else:
            self.estatisticas[(self.tamanho_chunk, numero_destinos, tamanho)].append(tempo_sem_escrita)

        print(f"\nDownload do arquivo {arquivo_escolhido} finalizado.")

        print()

    def exibir_estatisticas(self):
        print(f"{'Tam. chunk':>11} | {'N peers':>7} | {'Tam. arquivo':>13} | {'N':>2} | {'Tempo [s]':>10} | {'Desvio':>7}")
        print("-" * 65)

        for (chunk, n_peers, tam_arq), tempos in self.estatisticas.items():
            n = len(tempos)
            media = statistics.mean(tempos)
            desvio = statistics.stdev(tempos) if n > 1 else 0.0

            print(f"{chunk:11} | {n_peers:7} | {tam_arq:13} | {n:2} | {media:10.5f} | {desvio:7.5f}")

        print()

    def altera_tamanho_chunk(self):
        print("Digite novo tamanho de chunk:")
        novo_tamanho_chunk = int(input("> "))

        self.tamanho_chunk = novo_tamanho_chunk
        print(f"\n        Tamanho de chunk alterado: {self.tamanho_chunk}\n")

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
                self.exibir_estatisticas()
            elif comando == "6":
                self.altera_tamanho_chunk()
            elif comando == "9":
                self.sair()
                break
            else:
                print("Comando não conhecido\n")
