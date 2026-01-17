def get_die_cellLevel(id_str: str) -> tuple:
    die_cellLevel = int(id_str[5], 16)
    return ["1","2","4","8"][die_cellLevel%4], ["SLC","MLC","TLC","QLC"][die_cellLevel//4]