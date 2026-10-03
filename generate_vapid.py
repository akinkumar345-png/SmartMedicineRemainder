from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives import serialization
import base64

# Generate VAPID private key
private_key = ec.generate_private_key(ec.SECP256R1())

# Get DER bytes
der_private = private_key.private_bytes(
    encoding=serialization.Encoding.DER,
    format=serialization.PrivateFormat.TraditionalOpenSSL,
    encryption_algorithm=serialization.NoEncryption()
)

# Convert DER to Base64 text
private_key_base64 = base64.b64encode(der_private).decode()

# Save as text
with open("vapid_private.txt", "w") as f:
    f.write(private_key_base64)

# Generate public key
public_key = private_key.public_key()

raw_public = public_key.public_bytes(
    encoding=serialization.Encoding.X962,
    format=serialization.PublicFormat.UncompressedPoint
)

public_key_base64 = base64.urlsafe_b64encode(
    raw_public
).rstrip(b"=").decode()

print("PUBLIC KEY:")
print(public_key_base64)
print()
print("Private key file created: vapid_private.txt")