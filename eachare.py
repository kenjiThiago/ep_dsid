import sys
from classes import Peer
import threading

args = sys.argv

diretorio_compartilhado = args.pop()
arquivo_vizinhos = args.pop()

ip, porta = args.pop().split(":")

peer = Peer(ip, int(porta), arquivo_vizinhos, diretorio_compartilhado)

thread_servidor = threading.Thread(target = peer.inicia_servidor, daemon = True)

thread_servidor.start()

while True:
    comando = int(input('''Escolha um comando:
        [1] Listar peers
        [2] Obter peers
        [3] Listar arquivos locais
        [4] Buscar arquivos
        [5] Exibir estatisticas
        [6] Alterar tamanho de chunk
        [9] Sair
> '''))
    print()

    match comando:
        case 1:
            peer.lista_peers()
        case 2:
            peer.obter_peers()
        case 3:
            peer.lista_arquivos_locais()
        case 9:
            peer.sair()
            break
        case _:
            print("Comando não conhecido")
