import re
from pathlib import Path

from setuptools import setup, find_packages

# 版本号单一来源：epycon/__init__.py 的 __version__
version = re.search(
    r"__version__\s*=\s*['\"]([^'\"]+)['\"]",
    Path(__file__).with_name('epycon').joinpath('__init__.py').read_text(encoding='utf-8'),
).group(1)

setup(
    name='epycon',
    version=version,
    description='Parsing and converting Abbott WorkMate EP data into open formats '
                '(fork of FNUSA-ICRC epycon, with Web UI)',
    url='https://github.com/flyskyman/epycon-webui',
    author='flyskyman',
    author_email='flyskyman@gmail.com',
    packages=find_packages(),
    install_requires=[
        'h5py',
        'jsonschema',
        'numpy',
        ],
    classifiers=[
        'Programming Language :: Python :: 3',
        'Operating System :: OS Independent',
        ],
    zip_safe=False,
      )
