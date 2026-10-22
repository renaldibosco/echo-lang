"""Cyber-security learning tools: hashes, encodings, classic ciphers, password checks.
Everything runs locally; nothing is sent anywhere."""
import base64
import hashlib
import math
import secrets
import string

from ..errors import EchoRuntimeError
from ..values import show
from . import builtin

Y = "cyber"


def _bytes(t):
    return show(t).encode("utf-8")


for _name in ("md5", "sha1", "sha256", "sha512"):
    builtin(_name, Y, "%s(text) hash as hex" % _name)(
        (lambda algo: lambda text: hashlib.new(algo, _bytes(text)).hexdigest())(_name))


@builtin("base64_encode", Y, "base64_encode(text)")
def _b64e(t):
    return base64.b64encode(_bytes(t)).decode()


@builtin("base64_decode", Y, "base64_decode(text)")
def _b64d(t):
    try:
        return base64.b64decode(show(t), validate=True).decode("utf-8", "replace")
    except Exception:
        raise EchoRuntimeError("That is not valid Base64.")


@builtin("hex_encode", Y, "hex_encode(text) -> hex")
def _hexe(t):
    return _bytes(t).hex()


@builtin("hex_decode", Y, "hex_decode(hex) -> text")
def _hexd(h):
    try:
        return bytes.fromhex(show(h)).decode("utf-8", "replace")
    except ValueError:
        raise EchoRuntimeError("That is not valid hex.")


def _shift(t, k):
    out = []
    for ch in show(t):
        if "a" <= ch <= "z":
            out.append(chr((ord(ch) - 97 + k) % 26 + 97))
        elif "A" <= ch <= "Z":
            out.append(chr((ord(ch) - 65 + k) % 26 + 65))
        else:
            out.append(ch)
    return "".join(out)


@builtin("caesar", Y, "caesar(text, shift) Caesar cipher (negative shift decodes)")
def _caesar(t, k):
    return _shift(t, int(k))


@builtin("rot13", Y, "rot13(text)")
def _rot13(t):
    return _shift(t, 13)


@builtin("caesar_crack", Y, "caesar_crack(text) list of all 26 shifts to read by eye")
def _crack(t):
    return ["%2d: %s" % (k, _shift(t, -k)) for k in range(26)]


@builtin("vigenere", Y, "vigenere(text, key, decode=false)")
def _vigenere(t, key, decode=False):
    key = [ord(c) - 65 for c in show(key).upper() if c.isalpha()]
    if not key:
        raise EchoRuntimeError("vigenere() needs a key with letters.")
    out, i = [], 0
    for ch in show(t):
        if ch.isalpha() and ch.isascii():
            k = key[i % len(key)] * (-1 if decode else 1)
            out.append(_shift(ch, k))
            i += 1
        else:
            out.append(ch)
    return "".join(out)


@builtin("xor_cipher", Y, "xor_cipher(text, key) -> hex; xor_decipher(hex, key) reverses it")
def _xor(t, key):
    k = _bytes(key)
    if not k:
        raise EchoRuntimeError("xor_cipher() needs a key.")
    return bytes(b ^ k[i % len(k)] for i, b in enumerate(_bytes(t))).hex()


@builtin("xor_decipher", Y, "xor_decipher(hex, key)")
def _xord(h, key):
    k = _bytes(key)
    data = bytes.fromhex(show(h))
    return bytes(b ^ k[i % len(k)] for i, b in enumerate(data)).decode("utf-8", "replace")


@builtin("entropy", Y, "entropy(text) Shannon entropy in bits per character")
def entropy(t):
    t = show(t)
    if not t:
        return 0
    n = len(t)
    return round(-sum(t.count(c) / n * math.log2(t.count(c) / n) for c in set(t)), 4)


@builtin("password_strength", Y, "password_strength(pw) map: score 0-4, label, tips")
def _strength(pw):
    pw = show(pw)
    pool = 0
    tips = []
    if any(c.islower() for c in pw):
        pool += 26
    else:
        tips.append("add lower-case letters")
    if any(c.isupper() for c in pw):
        pool += 26
    else:
        tips.append("add capital letters")
    if any(c.isdigit() for c in pw):
        pool += 10
    else:
        tips.append("add numbers")
    if any(not c.isalnum() for c in pw):
        pool += 32
    else:
        tips.append("add symbols")
    if len(pw) < 12:
        tips.append("use 12 or more characters")
    bits = len(pw) * math.log2(pool) if pool else 0
    common = pw.lower() in ("password", "123456", "12345678", "qwerty", "admin", "letmein", "iloveyou")
    score = 0 if common else (0 if bits < 28 else 1 if bits < 36 else 2 if bits < 60 else 3 if bits < 80 else 4)
    if common:
        tips.insert(0, "this is a very common password")
    labels = ["very weak", "weak", "fair", "strong", "very strong"]
    return {"score": score, "label": labels[score], "bits": round(bits, 1), "tips": tips}


@builtin("random_password", Y, "random_password(length=16) strong random password")
def _random_password(n=16):
    alphabet = string.ascii_letters + string.digits + "!@#$%^&*-_=+"
    return "".join(secrets.choice(alphabet) for _ in range(int(n)))


@builtin("is_valid_ip", Y, "is_valid_ip(text) true for a valid IPv4 address")
def _is_ip(t):
    parts = show(t).split(".")
    return len(parts) == 4 and all(p.isdigit() and 0 <= int(p) <= 255 and str(int(p)) == p for p in parts)
