from setuptools import setup, find_packages

setup(
    name="neurafs",
    version="2.0.0",
    packages=find_packages(include=["neurafs", "neurafs.*"]),
)