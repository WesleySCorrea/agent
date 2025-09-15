import os
import json
import time
import socket
import shutil
import platform
import traceback
from datetime import datetime
from dotenv import load_dotenv

import pika

import mimetypes


# ----------------- Config (override por env) -----------------
load_dotenv()

RABBITMQ_URL = os.getenv("RABBITMQ_URL")
QUEUE_NAME   = os.getenv("QUEUE_NAME")
BASE_PATH    = os.getenv("BASE_PATH")

print("\n[agent] ===== CONFIG ATIVA =====")
print(f"[agent] RABBITMQ_URL = {RABBITMQ_URL}")
print(f"[agent] QUEUE_NAME   = {QUEUE_NAME}")
print(f"[agent] BASE_PATH    = {BASE_PATH}")
print("[agent] ========================\n")

# ----------------- Execução de comando permitido -----------------
ALLOWED_COMMANDS = {"ls", "mkdir", "rm", "down", "copy", "rename", "open", "save", "listdown"}  # whitelist

if platform.system().lower().startswith("win"):
    import ctypes
    from ctypes import wintypes

    GetFileAttributesW = ctypes.windll.kernel32.GetFileAttributesW
    GetFileAttributesW.argtypes = [wintypes.LPCWSTR]
    GetFileAttributesW.restype = wintypes.DWORD

    def _win_attrs(path: str):
        attrs = GetFileAttributesW(path)
        if attrs == 0xFFFFFFFF:
            return 0
        return attrs

    def is_hidden(path: str) -> bool:
        return bool(_win_attrs(path) & 0x2)

    def is_system(path: str) -> bool:
        return bool(_win_attrs(path) & 0x4)

else:

    # ----------------- Funções Linux/macOS -----------------
    def is_hidden(path: str) -> bool:
        return os.path.basename(path).startswith(".")


    def is_system(path: str) -> bool:
        return False

def list_dirs_including_hidden(target_path: str):
    items = []
    with os.scandir(target_path) as it:
        for entry in it:
            fullp = os.path.join(target_path, entry.name)
            try:
                st = entry.stat(follow_symlinks=False)
                ext = os.path.splitext(entry.name)[1]
                mime, _ = mimetypes.guess_type(fullp)

                if ext.lower() == ".ini":
                    continue

                hidden = is_hidden(fullp)
                system = is_system(fullp)

                items.append({
                    "name": entry.name,
                    "path": fullp,
                    "is_dir": entry.is_dir(follow_symlinks=False),
                    "is_file": entry.is_file(follow_symlinks=False),
                    "is_symlink": entry.is_symlink(),
                    "ext": ext,
                    "mime": mime,
                    "size": st.st_size,
                    "created": datetime.fromtimestamp(st.st_ctime).isoformat(),
                    "modified": datetime.fromtimestamp(st.st_mtime).isoformat(),
                    "accessed": datetime.fromtimestamp(st.st_atime).isoformat(),
                    "hidden": hidden,
                    "system": system
                })
            except PermissionError:
                pass
    return items

def make_dir(path: str):
    try:
        os.makedirs(path, exist_ok=True)
        return {"success": True, "path": path}
    except Exception as e:
        return {"success": False, "error": str(e)}

def delete_path(path: str):
    """
    Deleta um arquivo ou pasta (com conteúdo) de forma segura.
    Retorna dicionário com sucesso ou erro.
    """
    try:
        path = os.path.normpath(path.strip())

        if not os.path.exists(path):
            return {"success": False, "error": "Arquivo/pasta não existe", "path": path}

        if os.path.isfile(path):
            os.remove(path)
        elif os.path.isdir(path):
            shutil.rmtree(path)
        else:
            return {"success": False, "error": "Tipo desconhecido", "path": path}

        return {"success": True, "path": path}

    except Exception as e:
        return {"success": False, "error": str(e), "path": path}

def download_file(path: str, url: str):
    import requests
    import os

    if not url:
        return {"error": "nenhuma URL fornecida para download"}

    try:
        # Extrai o nome do arquivo da URL
        filename = os.path.basename(url.split("?")[0])
        local_path = os.path.join(path, filename)

        # Cria a pasta se não existir
        os.makedirs(path, exist_ok=True)

        # Baixa o arquivo
        r = requests.get(url, stream=True)
        r.raise_for_status()
        with open(local_path, "wb") as f:
            for chunk in r.iter_content(chunk_size=8192):
                f.write(chunk)

        return {"success": True, "downloaded_file": local_path}

    except Exception as e:
        return {"error": f"falha ao baixar: {str(e)}"}

def copy_file(source: str, target: str):
    import shutil, os
    try:
        if os.path.isdir(source):
            shutil.copytree(source, target, dirs_exist_ok=True)
        else:
            os.makedirs(os.path.dirname(target), exist_ok=True)
            shutil.copy2(source, target)
        return {"success": True}
    except Exception as e:
        return {"error": str(e)}

def rename_file(path: str, new_name: str):
    import os
    try:
        if not os.path.exists(path):
            return {"error": "Arquivo/pasta não existe"}

        # pasta do arquivo
        dir_path = os.path.dirname(path)
        # caminho completo do novo nome
        new_path = os.path.join(dir_path, new_name)

        os.rename(path, new_path)
        return {"success": True, "old_path": path, "new_path": new_path}

    except Exception as e:
        return {"error": str(e)}

def open_file(path: str):
    if not os.path.isfile(path):
        return {
            "status": "error",
            "message": f"O caminho não é um arquivo: {path}"
        }

    try:
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()

        return {
            "status": "ok",
            "path": path,
            "content": content
        }
    except Exception as e:
        return {
            "status": "error",
            "message": str(e),
            "path": path
        }

def save_file(path: str, content: str) -> dict:
    try:
        # Abre o arquivo em modo de escrita e sobrescreve o conteúdo
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)

        return {
            "success": True,
            "path": path,
            "size": len(content),
            "message": f"Arquivo salvo com sucesso em {path}"
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "path": path
        }

def handle_command(body: str):

    cmd = None
    path = BASE_PATH
    data = {}

    try:
        data = json.loads(body)
        cmd = str(data.get("cmd", "")).strip()
        if "path" in data and data["path"]:
            path = str(data["path"])
    except Exception:
        cmd = body.strip()

    if cmd not in ALLOWED_COMMANDS:
        return {"error": f"comando não permitido: {cmd}",
                "allowed": sorted(list(ALLOWED_COMMANDS))}

    if cmd == "ls":
        entries = list_dirs_including_hidden(path)
        return {
            "host": socket.gethostname(),
            "os": platform.platform(),
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "command": cmd,
            "path": path,
            "entries": entries
        }
    elif cmd == "mkdir":
        result = make_dir(path)
        return {
            "host": socket.gethostname(),
            "os": platform.platform(),
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "command": cmd,
            "path": path,
            **result
        }

    elif cmd == "rm":
        result = delete_path(path)
        return {
            "host": socket.gethostname(),
            "os": platform.platform(),
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "command": cmd,
            "path": path,
            **result
        }
    elif cmd == "down":
        url = data.get("url")
        result = download_file(path, url)
        return {
            "host": socket.gethostname(),
            "os": platform.platform(),
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "command": cmd,
            "path": path,
            **result
        }
    elif cmd == "listdown":
        path = BASE_PATH
        url = data.get("url")
        result = download_file(path, url)
        return {
            "host": socket.gethostname(),
            "os": platform.platform(),
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "command": cmd,
            "path": path,
            **result
        }
    elif cmd == "copy":
        old_path = data.get("oldPath")
        path = data.get("path")  # pasta destino
        if not old_path or not path:
            return {"error": "oldPath e path são obrigatórios para copy"}

        import os
        file_name = os.path.basename(old_path)  # pega só o nome do arquivo/pasta
        target_path = os.path.join(path, file_name)

        result = copy_file(old_path, target_path)
        return {
            "host": socket.gethostname(),
            "os": platform.platform(),
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "command": cmd,
            "source": old_path,
            "target": target_path,
            **result
        }
    elif cmd == "rename":
        path = data.get("path")
        name = data.get("name")
        if not name or not path:
            return {"error": "path e name são obrigatórios para rename"}

        result = rename_file(path, name)
        return {
            "host": socket.gethostname(),
            "os": platform.platform(),
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "command": cmd,
            **result
        }
    elif cmd == "open":
        path = data.get("path")
        if not path:
            return {"error": "path é obrigatório para open"}

        result = open_file(path)
        return {
            "host": socket.gethostname(),
            "os": platform.platform(),
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "command": cmd,
            **result
        }
    elif cmd == "save":
        path = data.get("path")
        content = data.get("content")
        if not path or not content:
            return {"error": "path e content são obrigatório para save"}

        result = save_file(path, content)
        return {
            "host": socket.gethostname(),
            "os": platform.platform(),
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "command": cmd,
            **result
        }

# ----------------- Rabbit consumer callback -----------------
def on_message(ch, method, properties, body):
    try:
        msg = body.decode("utf-8", errors="ignore")
        print(f"[agent] recebido: {msg}")
        payload = handle_command(msg)

        #Se veio como RPC: responder na fila de reply_to (Direct Reply-To)
        try:
            reply_to = getattr(properties, "reply_to", None)
            corr_id  = getattr(properties, "correlation_id", None)
            if reply_to:
                ch.basic_publish(
                    exchange="",
                    routing_key=reply_to,
                    properties=pika.BasicProperties(correlation_id=corr_id),
                    body=json.dumps(payload)
                )
                print(f"[agent] RPC reply enviado (corr_id={corr_id})")
        except Exception as e:
            print(f"[agent] erro ao responder RPC -> {e}")

        ch.basic_ack(delivery_tag=method.delivery_tag)

    except Exception:
        import traceback
        print("[agent] exceção no on_message:\n" + traceback.format_exc())
        try:
            ch.basic_nack(delivery_tag=method.delivery_tag, requeue=True)
        except Exception:
            pass


# ----------------- Main com polling (não-bloqueante) -----------------
def main():
    params = pika.URLParameters(RABBITMQ_URL)
    # tornar a conexão mais resiliente
    params.heartbeat = 30
    params.blocked_connection_timeout = 30
    params.socket_timeout = 30

    connection = None

    for i in range(10):
        try:
            print(f"[agent] conectando ao RabbitMQ... tent {i+1}/10")
            connection = pika.BlockingConnection(params)
            break
        except Exception as e:
            print(f"[agent] falha na conexão: {e}")
            time.sleep(2)

    if connection is None or connection.is_closed:
        print("[agent] não conectou no RabbitMQ, saindo.")
        return

    try:
        channel = connection.channel()
        channel.queue_declare(queue=QUEUE_NAME, durable=True)
        channel.basic_qos(prefetch_count=1)

        print(f"[agent] ouvindo fila '{QUEUE_NAME}' RABBITMQ_URL={RABBITMQ_URL}")
        print("[agente rodando e funcionando]")

        idle = 0
        while True:
            method_frame, header_frame, body = channel.basic_get(queue=QUEUE_NAME, auto_ack=False)
            if method_frame:
                on_message(channel, method_frame, header_frame, body)
                idle = 0
            else:
                idle += 1
                if idle % 5 == 0:
                    print("[agent] aguardando mensagens...")
                connection.process_data_events(time_limit=0.2)
                time.sleep(1)

    except KeyboardInterrupt:
        print("\n[agent] encerrando por Ctrl+C ...")
    except Exception:
        print("[agent] erro no loop principal:\n" + traceback.format_exc())
    finally:
        try:
            if connection and connection.is_open:
                connection.close()
        except Exception:
            pass
        print("[agent] terminado.")

if __name__ == "__main__":
    main()

