from setuptools import setup, find_packages

setup(
    name="neurafs",
    version="2.3.0",
    packages=find_packages(),
    entry_points={
        "console_scripts": [
            "neurafs=neurafs.cli:main",
        ],
    },
)