from sqlalchemy import inspect
from sqlalchemy.types import Float, Numeric


def schema_problems(engine, metadata):
    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())
    problems = []
    for table in metadata.sorted_tables:
        if table.name not in existing_tables:
            problems.append(f'缺少表 {table.name}')
            continue
        columns = {column['name']: column for column in inspector.get_columns(table.name)}
        for column in table.columns:
            if column.name not in columns:
                problems.append(f'缺少列 {table.name}.{column.name}')
                continue
            expected = column.type
            actual = columns[column.name]['type']
            if (engine.dialect.name == 'mysql' and isinstance(expected, Numeric)
                    and not isinstance(expected, Float)
                    and (not isinstance(actual, Numeric) or isinstance(actual, Float)
                         or actual.precision != expected.precision or actual.scale != expected.scale)):
                problems.append(f'数值类型不匹配 {table.name}.{column.name}（期望 {expected}，实际 {actual}）')
    return problems
