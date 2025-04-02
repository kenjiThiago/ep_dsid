import sys
from peer import Peer
import threading

args = sys.argv

if len(args) < 4:
    print("Não foram passados todos os argumentos")
    exit(1)

diretorio_compartilhado = args.pop()
arquivo_vizinhos = args.pop()

ip, porta = args.pop().split(":")

peer = Peer(ip, int(porta), arquivo_vizinhos, diretorio_compartilhado)

thread_servidor = threading.Thread(target = peer.inicia_servidor, daemon = True)
thread_servidor.start()

thread_cliente = threading.Thread(target = peer.inicia_cliente, daemon = True)
thread_cliente.start()

thread_servidor.join()
thread_cliente.join()
