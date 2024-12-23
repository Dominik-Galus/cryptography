import random

import numpy as np
from pydantic import Field

from cryptography.data.aes_constants import inv_s_box, rcon, s_box
from cryptography.keys.symmetric.symmetric import Symmetric


class AES(Symmetric):
    key_columns: int = Field(default=0)
    rounds: int = Field(default=0)
    expanded_key: np.ndarray = Field(default=np.empty(0))
    state: np.ndarray = Field(default=np.empty(0))

    def __init__(
        self, bits: int, aes_key: np.ndarray | list[str] | None = None,
    ) -> None:
        super().__init__(key=np.empty(0))
        if bits not in [128, 192, 256]:
            msg: str = "Wrong bits key length"
            raise ValueError(msg)
        self.key_columns: int = bits // 32
        self.rounds: int = {128: 10, 192: 12, 256: 14}[bits]
        if aes_key is not None:
            self.key = np.array(aes_key, dtype=np.uint8).reshape(4, self.key_columns)
        else:
            self.key = self.generate_key(bits)

        self.key_expansion()

    def rot_word(self, word: np.ndarray) -> np.ndarray:
        return np.roll(word, -1)

    def sub_word(self, word: np.ndarray) -> np.ndarray:
        return s_box[word // 16, word % 16]

    def generate_key(self, bits: int) -> np.ndarray:
        bytes_length: int = bits // 8
        hex_key: str = "".join(
            random.choice("0123456789abcdef") for _ in range(bytes_length * 2)
        )
        byte_array = np.array(
            [int(hex_key[i : i + 2], 16) for i in range(0, len(hex_key), 2)],
        )
        matrix = np.array([byte_array[i : i + 4] for i in range(0, len(byte_array), 4)])
        return matrix.T

    def key_expansion(self) -> None:
        self.expanded_key: np.ndarray = np.zeros(
            (4 * (self.rounds + 1), 4), dtype=np.uint8,
        )

        self.expanded_key[: self.key_columns] = self.key.T

        for i in range(self.key_columns, 4 * (self.rounds + 1)):
            temp: np.ndarray = self.expanded_key[i - 1].copy()

            if i % self.key_columns == 0:
                temp = self.sub_word(self.rot_word(temp))
                rcon_index = i // self.key_columns - 1
                rcon_value = rcon[rcon_index]
                rcon_value_array = np.array([rcon_value, 0, 0, 0], dtype=np.uint8)
                temp = temp ^ rcon_value_array
            elif self.key_columns > 6 and i % self.key_columns == 4:
                temp = self.sub_word(temp)

            self.expanded_key[i] = self.expanded_key[i - self.key_columns] ^ temp

    def aes_state(self, text: str) -> np.ndarray:
        byte_array = np.array([ord(char) for char in text.ljust(16)])
        state: np.ndarray = byte_array.reshape(4, 4).T
        return state

    def int_matrix_to_hex_matrix(self, matrix: np.ndarray) -> np.ndarray:
        return np.array([[f"{num:02x}" for num in row] for row in matrix])

    def sub_bytes(self) -> None:
        self.state = s_box[self.state // 16, self.state % 16]

    def shift_rows(self) -> None:
        for i in range(4):
            self.state[i] = np.roll(self.state[i], -i)

    def galois_mult(self, a: int, b: int) -> int:
        p: int = 0
        for _ in range(8):
            if b & 1:
                p ^= a
            carry = a & 0x80
            a <<= 1
            if carry:
                a ^= 0x1B
            b >>= 1
        return p & 0xFF

    def mix_columns(self) -> None:
        for i in range(4):
            col = self.state[:, i]
            self.state[:, i] = [
                self.galois_mult(col[0], 2)
                ^ self.galois_mult(col[1], 3)
                ^ self.galois_mult(col[2], 1)
                ^ self.galois_mult(col[3], 1),
                self.galois_mult(col[0], 1)
                ^ self.galois_mult(col[1], 2)
                ^ self.galois_mult(col[2], 3)
                ^ self.galois_mult(col[3], 1),
                self.galois_mult(col[0], 1)
                ^ self.galois_mult(col[1], 1)
                ^ self.galois_mult(col[2], 2)
                ^ self.galois_mult(col[3], 3),
                self.galois_mult(col[0], 3)
                ^ self.galois_mult(col[1], 1)
                ^ self.galois_mult(col[2], 1)
                ^ self.galois_mult(col[3], 2),
            ]

    def add_round_key(self, rounds: int) -> None:
        self.state ^= self.expanded_key[rounds * 4 : (rounds + 1) * 4].T

    def encrypt(self, message: str) -> str:
        padded_message = message.ljust((len(message) + 15) // 16 * 16)
        encrypted_message = ""

        for i in range(0, len(padded_message), 16):
            block = padded_message[i : i + 16]
            self.state: np.ndarray = self.aes_state(block)
            self.add_round_key(0)

            for iteration in range(1, self.rounds):
                self.sub_bytes()
                self.shift_rows()
                self.mix_columns()
                self.add_round_key(iteration)

            self.sub_bytes()
            self.shift_rows()
            self.add_round_key(self.rounds)

            encrypted_message += "".join(
                [f"{num:02x}" for num in self.state.T.flatten()],
            )

        return encrypted_message

    def inv_mix_columns(self) -> None:
        for i in range(4):
            col = self.state[:, i]
            self.state[:, i] = [
                self.galois_mult(col[0], 14)
                ^ self.galois_mult(col[1], 11)
                ^ self.galois_mult(col[2], 13)
                ^ self.galois_mult(col[3], 9),
                self.galois_mult(col[0], 9)
                ^ self.galois_mult(col[1], 14)
                ^ self.galois_mult(col[2], 11)
                ^ self.galois_mult(col[3], 13),
                self.galois_mult(col[0], 13)
                ^ self.galois_mult(col[1], 9)
                ^ self.galois_mult(col[2], 14)
                ^ self.galois_mult(col[3], 11),
                self.galois_mult(col[0], 11)
                ^ self.galois_mult(col[1], 13)
                ^ self.galois_mult(col[2], 9)
                ^ self.galois_mult(col[3], 14),
            ]

    def inv_shift_rows(self) -> None:
        for i in range(4):
            self.state[i] = np.roll(self.state[i], i)

    def inv_sub_bytes(self) -> None:
        self.state = inv_s_box[self.state // 16, self.state % 16]

    def decrypt(self, encrypted_message: str) -> str:
        decrypted_text: str = ""

        for i in range(0, len(encrypted_message), 32):
            block: str = encrypted_message[i : i + 32]
            byte_array = np.array(
                [int(block[j : j + 2], 16) for j in range(0, 32, 2)], dtype=np.uint8,
            )
            self.state = byte_array.reshape(4, 4).T

            self.add_round_key(self.rounds)

            for iteration in range(self.rounds - 1, 0, -1):
                self.inv_shift_rows()
                self.inv_sub_bytes()
                self.add_round_key(iteration)
                self.inv_mix_columns()

            self.inv_shift_rows()
            self.inv_sub_bytes()
            self.add_round_key(0)

            decrypted_text += "".join([chr(byte) for byte in self.state.T.flatten()])

        return decrypted_text.rstrip()


if __name__ == "__main__":
    AES(None, None)
