import sys
sys.path.insert(0, 'src')
from transport.setup import generate_setup_il
token = 'smoketok001'
root = '/home/Gent/.virtuoso-bridge'
port = 65081
text = generate_setup_il(
    daemon=f'{root}/{token}/ramic/ramic_bridge_daemon_3.py',
    il=f'{root}/{token}/ramic/ramic_bridge.il',
    python_cmd='python3',
    port=port,
    token=token,
    identity=f'{root}/{token}/status/daemon_identity.txt',
)
path = r'C:\Users\user\Desktop\repos_Github\virtuoso-bridge-NCS\tmp_vb_smoke_141b875b\virtuoso_setup.il'
open(path, 'w', encoding='utf-8').write(text)
print(path)
print(text)
