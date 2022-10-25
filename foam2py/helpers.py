import linecache
import re
from pathlib import Path
from typing import Callable, Union

import numpy as np
import pandas as pd

REGEX_FLOAT = r'[+-]?(\d+(\.\d*)?|\.\d+)([eE][+-]?\d+)?'


def is_notebook() -> bool:
    """Check if current file is IPython notebook."""

    try:
        shell = get_ipython().__class__.__name__
        if shell == 'ZMQInteractiveShell':
            return True  # Jupyter notebook or qtconsole
        elif shell == 'TerminalInteractiveShell':
            return False  # Terminal running IPython
        else:
            return False  # Other type (?)
    except NameError:
        return False


def count_columns(filepath: Union[Path, str],
                  sep: str,
                  line_no: int = 1) -> int:
    """Count columns in a data-file by counting separators in a line."""

    line = linecache.getline(str(Path(filepath)), line_no)
    return line.count(sep) + line.count('\n')


def load_dat(filepath: Union[Path, str],
             *,
             usecols: list = None,
             use_nth: int = None) -> pd.DataFrame:
    """Load OpenFOAM post-processing .dat file as pandas DataFrame."""

    def get_header_size(filepath: Union[Path, str], comment: str = '#') -> int:
        """Get header size."""

        with open(filepath) as f:
            for index, line in enumerate(f):
                if not line.startswith(comment):
                    return index - 1

    def unnest_columns(dat: pd.DataFrame) -> pd.DataFrame:
        """Unnest non-scalar field values to components."""

        nested_columns: list = []
        for key, column_dtype in zip(dat, dat.dtypes):
            if (column_dtype == np.dtype('object')
                    and re.match(rf'.*?{REGEX_FLOAT}', dat[key].iloc[-1])):

                fn = lambda cell: np.array(cell.replace('(', '').replace(
                    ')', '').split(),
                                           dtype=float)
                dat[key] = dat[key].apply(fn)

                pos, field = (dat.columns.to_list().index(key) + 1,
                              np.array(dat[key].to_list()))
                for component in range(field.shape[-1]):
                    dat.insert(pos + component, f'{key}.{component}',
                               field[:, component])

                nested_columns.append(key)

        return dat.drop(nested_columns, axis='columns')

    def load(filepath: Path) -> pd.DataFrame:

        header_pos = get_header_size(filepath)

        # Read .dat-file as pandas' DataFrame
        dat = pd.read_csv(
            filepath,
            sep='\t',
            header=header_pos,
            index_col=0,
            usecols=(usecols if usecols is None else ([0] + usecols)),
            skiprows=(lambda n: n > header_pos and n % use_nth
                      if not use_nth is None and use_nth >= 2 else None),
        )

        # Drop '#' and trails spaces from column names
        dat.index.name = dat.index.name.replace('#', '').strip()
        dat.columns = dat.columns.str.strip()

        return unnest_columns(dat)

    filepath = Path(filepath)

    # Merge all .dat-files in the direcotry into one dataframe
    if filepath.is_dir():
        filepaths = list(filepath.rglob('*.dat'))
        if len({fp.name for fp in filepaths}) != 1:
            raise ValueError(f'{filepath} is not valid')

        return pd.concat([load(dat_file) for dat_file in sorted(filepaths)])

    return load(filepath)


def load_xy(filepath: Union[Path, str],
            *,
            usecols: list = None,
            use_nth: int = None) -> pd.DataFrame:
    """Load OpenFOAM post-processing .xy file as pandas DataFrame."""

    def field_components(field_name: str, components_count: int) -> list:
        if components_count <= 1:
            return [field_name]
        elif components_count == 3:
            components = 'xyz'
        elif components_count == 6:
            components = ['xx', 'xy', 'xz', 'yy', 'yz', 'zz']
        else:
            components = range(components_count)

        return [f'{field_name}.{component}' for component in components]

    filepath = Path(filepath)

    # Get field names by splitting the filename
    field_names = filepath.stem.split('_')

    columns_count = count_columns(filepath, sep='\t')

    # Get position of the first column with field value
    pos = 0
    if not (columns_count - 1) % len(field_names[1:]):
        pos = 1
    elif columns_count > 3 and not (columns_count - 3) % len(field_names[3:]):
        pos = 3

    # Constuct field names by appending components
    components_count = (columns_count - pos) / len(field_names[pos:])
    names = field_components(field_names[0], pos)
    for field_name in field_names[pos:]:
        names += field_components(field_name, components_count)

    return pd.read_csv(
        filepath,
        sep='\t',
        index_col=0,
        usecols=usecols if usecols is None else ([0] + usecols),
        names=names,
        skiprows=(lambda n: n % use_nth
                  if not use_nth is None and use_nth >= 2 else None),
    )
