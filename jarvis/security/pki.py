"""
JARVIS PKI (Public Key Infrastructure)

Handles certificate generation and management for secure
server-client communication using mTLS.
"""

import os
import subprocess
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Tuple

from loguru import logger

try:
    from cryptography import x509
    from cryptography.x509.oid import NameOID, ExtendedKeyUsageOID
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.hazmat.backends import default_backend
    CRYPTOGRAPHY_AVAILABLE = True
except ImportError:
    CRYPTOGRAPHY_AVAILABLE = False
    logger.debug("cryptography not available. Install with: pip install cryptography")


class CertificateAuthority:
    """
    Manages a self-signed Certificate Authority for JARVIS.
    
    Creates and signs certificates for server and clients.
    """
    
    def __init__(self, cert_dir: str = "certs"):
        self.cert_dir = Path(cert_dir)
        self.ca_key_path = self.cert_dir / "ca.key"
        self.ca_cert_path = self.cert_dir / "ca.crt"
        
        self._ca_key = None
        self._ca_cert = None
    
    def initialize(self, force: bool = False) -> bool:
        """
        Initialize the Certificate Authority.
        
        Creates CA key and certificate if they don't exist.
        
        Args:
            force: If True, regenerate even if exists
        
        Returns:
            True if successful
        """
        if not CRYPTOGRAPHY_AVAILABLE:
            logger.error("cryptography package not installed")
            return False
        
        self.cert_dir.mkdir(parents=True, exist_ok=True)
        
        if not force and self.ca_key_path.exists() and self.ca_cert_path.exists():
            logger.info("CA already exists, loading...")
            return self._load_ca()
        
        logger.info("Generating new Certificate Authority...")
        
        try:
            # Generate CA private key
            self._ca_key = rsa.generate_private_key(
                public_exponent=65537,
                key_size=4096,
                backend=default_backend(),
            )
            
            # CA subject
            subject = issuer = x509.Name([
                x509.NameAttribute(NameOID.COUNTRY_NAME, "US"),
                x509.NameAttribute(NameOID.STATE_OR_PROVINCE_NAME, "California"),
                x509.NameAttribute(NameOID.ORGANIZATION_NAME, "JARVIS Home"),
                x509.NameAttribute(NameOID.COMMON_NAME, "JARVIS CA"),
            ])
            
            # Create CA certificate
            self._ca_cert = (
                x509.CertificateBuilder()
                .subject_name(subject)
                .issuer_name(issuer)
                .public_key(self._ca_key.public_key())
                .serial_number(x509.random_serial_number())
                .not_valid_before(datetime.utcnow())
                .not_valid_after(datetime.utcnow() + timedelta(days=3650))  # 10 years
                .add_extension(
                    x509.BasicConstraints(ca=True, path_length=None),
                    critical=True,
                )
                .add_extension(
                    x509.KeyUsage(
                        digital_signature=True,
                        key_cert_sign=True,
                        crl_sign=True,
                        key_encipherment=False,
                        content_commitment=False,
                        data_encipherment=False,
                        key_agreement=False,
                        encipher_only=False,
                        decipher_only=False,
                    ),
                    critical=True,
                )
                .sign(self._ca_key, hashes.SHA256(), default_backend())
            )
            
            # Save CA private key
            with open(self.ca_key_path, "wb") as f:
                f.write(self._ca_key.private_bytes(
                    encoding=serialization.Encoding.PEM,
                    format=serialization.PrivateFormat.TraditionalOpenSSL,
                    encryption_algorithm=serialization.NoEncryption(),
                ))
            
            # Secure the key file
            os.chmod(self.ca_key_path, 0o600)
            
            # Save CA certificate
            with open(self.ca_cert_path, "wb") as f:
                f.write(self._ca_cert.public_bytes(serialization.Encoding.PEM))
            
            logger.info(f"CA created: {self.ca_cert_path}")
            return True
            
        except Exception as e:
            logger.exception(f"Failed to create CA: {e}")
            return False
    
    def _load_ca(self) -> bool:
        """Load existing CA key and certificate."""
        try:
            with open(self.ca_key_path, "rb") as f:
                self._ca_key = serialization.load_pem_private_key(
                    f.read(),
                    password=None,
                    backend=default_backend(),
                )
            
            with open(self.ca_cert_path, "rb") as f:
                self._ca_cert = x509.load_pem_x509_certificate(
                    f.read(),
                    default_backend(),
                )
            
            logger.info("CA loaded successfully")
            return True
            
        except Exception as e:
            logger.error(f"Failed to load CA: {e}")
            return False
    
    def generate_server_cert(
        self,
        hostname: str = "jarvis-server",
        ip_addresses: list[str] = None,
        dns_names: list[str] = None,
        validity_days: int = 365,
    ) -> Tuple[Optional[Path], Optional[Path]]:
        """
        Generate a server certificate.
        
        Args:
            hostname: Server hostname
            ip_addresses: List of IP addresses for SAN
            dns_names: List of DNS names for SAN
            validity_days: Certificate validity in days
        
        Returns:
            (key_path, cert_path) or (None, None) on failure
        """
        if not self._ca_key or not self._ca_cert:
            logger.error("CA not initialized")
            return None, None
        
        try:
            # Generate server key
            key = rsa.generate_private_key(
                public_exponent=65537,
                key_size=2048,
                backend=default_backend(),
            )
            
            # Subject
            subject = x509.Name([
                x509.NameAttribute(NameOID.COUNTRY_NAME, "US"),
                x509.NameAttribute(NameOID.ORGANIZATION_NAME, "JARVIS Home"),
                x509.NameAttribute(NameOID.COMMON_NAME, hostname),
            ])
            
            # Build SAN (Subject Alternative Names)
            san_entries = []
            
            # Add DNS names
            dns_names = dns_names or [hostname, "localhost"]
            for dns in dns_names:
                san_entries.append(x509.DNSName(dns))
            
            # Add IP addresses
            ip_addresses = ip_addresses or ["127.0.0.1", "0.0.0.0"]
            for ip in ip_addresses:
                try:
                    import ipaddress
                    san_entries.append(x509.IPAddress(ipaddress.ip_address(ip)))
                except ValueError:
                    pass
            
            # Create certificate
            cert = (
                x509.CertificateBuilder()
                .subject_name(subject)
                .issuer_name(self._ca_cert.subject)
                .public_key(key.public_key())
                .serial_number(x509.random_serial_number())
                .not_valid_before(datetime.utcnow())
                .not_valid_after(datetime.utcnow() + timedelta(days=validity_days))
                .add_extension(
                    x509.BasicConstraints(ca=False, path_length=None),
                    critical=True,
                )
                .add_extension(
                    x509.KeyUsage(
                        digital_signature=True,
                        key_encipherment=True,
                        key_cert_sign=False,
                        crl_sign=False,
                        content_commitment=False,
                        data_encipherment=False,
                        key_agreement=False,
                        encipher_only=False,
                        decipher_only=False,
                    ),
                    critical=True,
                )
                .add_extension(
                    x509.ExtendedKeyUsage([
                        ExtendedKeyUsageOID.SERVER_AUTH,
                        ExtendedKeyUsageOID.CLIENT_AUTH,
                    ]),
                    critical=False,
                )
                .add_extension(
                    x509.SubjectAlternativeName(san_entries),
                    critical=False,
                )
                .sign(self._ca_key, hashes.SHA256(), default_backend())
            )
            
            # Save files
            key_path = self.cert_dir / "server.key"
            cert_path = self.cert_dir / "server.crt"
            
            with open(key_path, "wb") as f:
                f.write(key.private_bytes(
                    encoding=serialization.Encoding.PEM,
                    format=serialization.PrivateFormat.TraditionalOpenSSL,
                    encryption_algorithm=serialization.NoEncryption(),
                ))
            
            os.chmod(key_path, 0o600)
            
            with open(cert_path, "wb") as f:
                f.write(cert.public_bytes(serialization.Encoding.PEM))
            
            logger.info(f"Server certificate created: {cert_path}")
            return key_path, cert_path
            
        except Exception as e:
            logger.exception(f"Failed to generate server certificate: {e}")
            return None, None
    
    def generate_client_cert(
        self,
        client_id: str,
        hostname: str = None,
        validity_days: int = 365,
    ) -> Tuple[Optional[Path], Optional[Path]]:
        """
        Generate a client certificate.
        
        Args:
            client_id: Unique client identifier
            hostname: Client hostname
            validity_days: Certificate validity in days
        
        Returns:
            (key_path, cert_path) or (None, None) on failure
        """
        if not self._ca_key or not self._ca_cert:
            logger.error("CA not initialized")
            return None, None
        
        hostname = hostname or client_id
        
        try:
            # Generate client key
            key = rsa.generate_private_key(
                public_exponent=65537,
                key_size=2048,
                backend=default_backend(),
            )
            
            # Subject
            subject = x509.Name([
                x509.NameAttribute(NameOID.COUNTRY_NAME, "US"),
                x509.NameAttribute(NameOID.ORGANIZATION_NAME, "JARVIS Home"),
                x509.NameAttribute(NameOID.ORGANIZATIONAL_UNIT_NAME, "Clients"),
                x509.NameAttribute(NameOID.COMMON_NAME, hostname),
            ])
            
            # Create certificate
            cert = (
                x509.CertificateBuilder()
                .subject_name(subject)
                .issuer_name(self._ca_cert.subject)
                .public_key(key.public_key())
                .serial_number(x509.random_serial_number())
                .not_valid_before(datetime.utcnow())
                .not_valid_after(datetime.utcnow() + timedelta(days=validity_days))
                .add_extension(
                    x509.BasicConstraints(ca=False, path_length=None),
                    critical=True,
                )
                .add_extension(
                    x509.KeyUsage(
                        digital_signature=True,
                        key_encipherment=True,
                        key_cert_sign=False,
                        crl_sign=False,
                        content_commitment=False,
                        data_encipherment=False,
                        key_agreement=False,
                        encipher_only=False,
                        decipher_only=False,
                    ),
                    critical=True,
                )
                .add_extension(
                    x509.ExtendedKeyUsage([
                        ExtendedKeyUsageOID.CLIENT_AUTH,
                    ]),
                    critical=False,
                )
                .sign(self._ca_key, hashes.SHA256(), default_backend())
            )
            
            # Save files in client subdirectory
            client_dir = self.cert_dir / "clients" / client_id
            client_dir.mkdir(parents=True, exist_ok=True)
            
            key_path = client_dir / "client.key"
            cert_path = client_dir / "client.crt"
            
            with open(key_path, "wb") as f:
                f.write(key.private_bytes(
                    encoding=serialization.Encoding.PEM,
                    format=serialization.PrivateFormat.TraditionalOpenSSL,
                    encryption_algorithm=serialization.NoEncryption(),
                ))
            
            os.chmod(key_path, 0o600)
            
            with open(cert_path, "wb") as f:
                f.write(cert.public_bytes(serialization.Encoding.PEM))
            
            # Also copy CA cert for the client
            ca_copy = client_dir / "ca.crt"
            with open(ca_copy, "wb") as f:
                f.write(self._ca_cert.public_bytes(serialization.Encoding.PEM))
            
            logger.info(f"Client certificate created: {cert_path}")
            return key_path, cert_path
            
        except Exception as e:
            logger.exception(f"Failed to generate client certificate: {e}")
            return None, None
    
    def verify_certificate(self, cert_path: str) -> bool:
        """Verify a certificate is signed by our CA."""
        if not self._ca_cert:
            return False
        
        try:
            with open(cert_path, "rb") as f:
                cert = x509.load_pem_x509_certificate(f.read(), default_backend())
            
            # Check if signed by our CA
            try:
                self._ca_cert.public_key().verify(
                    cert.signature,
                    cert.tbs_certificate_bytes,
                    cert.signature_algorithm_parameters,
                )
                return True
            except Exception:
                return False
                
        except Exception as e:
            logger.error(f"Certificate verification failed: {e}")
            return False


def generate_certificates_cli():
    """Command-line interface for certificate generation."""
    import argparse
    
    parser = argparse.ArgumentParser(description="JARVIS Certificate Manager")
    parser.add_argument("command", choices=["init", "server", "client"])
    parser.add_argument("--cert-dir", default="certs", help="Certificate directory")
    parser.add_argument("--client-id", help="Client ID for client cert")
    parser.add_argument("--hostname", help="Hostname for certificate")
    parser.add_argument("--ip", action="append", help="IP address for SAN")
    parser.add_argument("--force", action="store_true", help="Force regeneration")
    
    args = parser.parse_args()
    
    ca = CertificateAuthority(args.cert_dir)
    
    if args.command == "init":
        if ca.initialize(force=args.force):
            print("✅ CA initialized successfully")
        else:
            print("❌ CA initialization failed")
            exit(1)
    
    elif args.command == "server":
        if not ca.initialize():
            print("❌ Failed to load CA")
            exit(1)
        
        key, cert = ca.generate_server_cert(
            hostname=args.hostname or "jarvis-server",
            ip_addresses=args.ip or ["127.0.0.1"],
        )
        
        if key and cert:
            print(f"✅ Server certificate created:")
            print(f"   Key:  {key}")
            print(f"   Cert: {cert}")
        else:
            print("❌ Server certificate generation failed")
            exit(1)
    
    elif args.command == "client":
        if not args.client_id:
            print("❌ --client-id required for client certificate")
            exit(1)
        
        if not ca.initialize():
            print("❌ Failed to load CA")
            exit(1)
        
        key, cert = ca.generate_client_cert(
            client_id=args.client_id,
            hostname=args.hostname,
        )
        
        if key and cert:
            print(f"✅ Client certificate created:")
            print(f"   Key:  {key}")
            print(f"   Cert: {cert}")
            print(f"   CA:   {key.parent / 'ca.crt'}")
        else:
            print("❌ Client certificate generation failed")
            exit(1)


if __name__ == "__main__":
    generate_certificates_cli()
