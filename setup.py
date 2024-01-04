from setuptools import setup, find_packages

def read_requirements(file_path):
    with open(file_path, 'r') as file:
        return [line.strip() for line in file if line.strip()]

setup(
    name='flixOpt',
    version='0.1.0',
    packages=find_packages(exclude=['tests', 'docs', '.git', '.vscode', 'build', '.venv']),
    install_requires=read_requirements('requirements.txt')
)
