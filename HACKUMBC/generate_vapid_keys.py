from cryptography.hazmat.primitives.serialization import Encoding
from py_vapid import Vapid


vapid = Vapid()
vapid.generate_keys()


private_key = vapid.private_key
public_key = vapid.public_key


with open("private_key.pem", "wb") as f:
    f.write(
        private_key.private_bytes(
            encoding=Encoding.PEM,
            format=private_key.private_bytes.__annotations__.get(
                "format"
            )
            if False
            else __import__(
                "cryptography.hazmat.primitives.serialization",
                fromlist=["PrivateFormat"]
            ).PrivateFormat.PKCS8,
            encryption_algorithm=__import__(
                "cryptography.hazmat.primitives.serialization",
                fromlist=["NoEncryption"]
            ).NoEncryption(),
        )
    )


with open("public_key.txt", "w") as f:
    f.write(
        public_key.public_bytes(
            Encoding.X962,
            __import__(
                "cryptography.hazmat.primitives.serialization",
                fromlist=["PublicFormat"]
            ).PublicFormat.UncompressedPoint,
        ).hex()
    )

print("VAPID keys generated.")
