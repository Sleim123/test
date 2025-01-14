# РАСШИФРОВЩИК JSON ФАЙЛОВ

import json
from cryptography.fernet import Fernet

# Загрузка ключа шифрования
def load_key():
    try:
        with open('encryption.key', 'rb') as key_file:
            return key_file.read()
    except FileNotFoundError:
        raise Exception("Файл 'encryption.key' не найден. Убедитесь, что он находится в той же папке.")

# Расшифровка данных
def decrypt_file(filename):
    try:
        key = load_key()
        fernet = Fernet(key)

        # Чтение зашифрованного файла
        with open(filename, 'rb') as file:
            encrypted_data = file.read()

        # Расшифровка данных
        decrypted_data = fernet.decrypt(encrypted_data).decode('utf-8')

        # Преобразование расшифрованных данных в JSON
        return json.loads(decrypted_data)
    except Exception as e:
        print(f"Ошибка при расшифровке файла {filename}: {e}")
        return None

# Пример использования
if __name__ == "__main__":
    filename = input("Введите имя файла для расшифровки (например, 'users.json'): ")

    data = decrypt_file(filename)
    if data is not None:
        print("Расшифрованные данные:")
        print(json.dumps(data, indent=4, ensure_ascii=False))
    else:
        print("Не удалось расшифровать данные.")
