# ГЕНЕРАТОР НОВОГО КЛЮЧА ШИФРОВАНИЯ (encryption.key)
# ПРИ ПОВТОРНОМ СОЗДАНИИ КЛЮЧА ШИФРОВАНИЯ JSON ФАЙЛЫ ПРИЙДЕТСЯ УДАЛИТЬ!

from cryptography.fernet import Fernet
import os

def generate_key():
    key = Fernet.generate_key()
    with open('encryption.key', 'wb') as key_file:
        key_file.write(key)
    print("Ключ шифрования успешно сгенерирован!")

generate_key()
