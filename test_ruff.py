def badly_formatted_function(x, y, z):
    unused_var = 5
    result = x + y + z
    return result


class TestClass:
    def __init__(self, name: str, value: int):
        self.name = name
        self.value = value

    def get_info(self):
        return f"{self.name}: {self.value}"
