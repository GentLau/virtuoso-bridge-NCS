import sys
sys.path.insert(0, 'src')
from transport.setup import generate_setup_il
token='smoketok027'; root='/home/Gent/.virtuoso-bridge'; port=65091
text=generate_setup_il(
    daemon=f'{root}/{token}/ramic/ramic_bridge_daemon_27.py',
    il=f'{root}/{token}/ramic/ramic_bridge.il',
    python_cmd='/opt/eda/cadence/XCELUMMAIN2309/tools.lnx86/python2.7/bin/python2.7',
    port=port, token=token,
    identity=f'{root}/{token}/status/daemon_identity.txt')
open(r'C:\Users\user\Desktop\repos_Github\virtuoso-bridge-NCS\tmp_vb_smoke27_f2b6e6da\virtuoso_setup.il','w',encoding='utf-8').write(text)
print(text)
