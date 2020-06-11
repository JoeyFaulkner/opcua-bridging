from asyncua.server.user_managers import CertificateUserManager
from asyncua import Server
from asyncua import ua
import yaml


async def server_with_certificates(server_url, server_certificate_path, server_private_key_path, certificates=None):
    """
    :param server_url:
    :type server_url: str
    :param server_certificate_path:
    :type server_certificate_path: str
    :param server_private_key_path:
    :type server_private_key_path: str
    :param certificates:
    :type certificates: list
    :return:
    """
    # setup our serverclone_and_subscribe(client_node, server_node, sub_handler)
    certificate_handler = CertificateUserManager()
    for role_add in certificates:
        certificate_path = role_add['certificate_path']
        name = role_add['name']
        role = role_add['role']
        if role == 'admin':
            await certificate_handler.add_admin(certificate_path=certificate_path, name=name)
        elif role == 'user':
            await certificate_handler.add_user(certificate_path=certificate_path, name=name)
        else:
            raise NotImplementedError

    server = Server(user_manager=certificate_handler)
    await server.init()
    server.set_endpoint(server_url)
    server.set_security_policy([ua.SecurityPolicyType.Basic256Sha256_SignAndEncrypt])

    await server.load_certificate(server_certificate_path)
    await server.load_private_key(server_private_key_path)
    return server, certificate_handler


async def server_from_yaml(yaml_path):
    out = yaml.safe_load(open(yaml_path, 'r'))
    server, _ = await server_with_certificates(out['server_url'], out['server_certificate_path'],
                                               out['server_private_key_path'], out['certificates'])
    return server

if __name__ == '__main__':
    import asyncio
    asyncio.run(server_from_yaml('examples/bridge/cloud/cloud_server_config.yaml'))