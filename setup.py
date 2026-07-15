from setuptools import setup, find_packages

setup(
    name='alpha',                # Your package name
    version='0.1.0',                  # Package version
    packages=find_packages(),         # Automatically find packages in your project
    author='alphateam',
    author_email='',
    install_requires=[
        'censusname',
        'matplotlib',
        'openai',        # used as OpenAI-compatible client for Groq / Mistral
        'ortools',
        'pandas',
        'plotnine',
        'protobuf',
        'pydantic',
        'python-dotenv',
        'setuptools',
        'tqdm',
        'requests'
    ],              # List of dependencies
    classifiers=[
        'Programming Language :: Python :: 3',
        'License :: OSI Approved :: MIT License',
        'Operating System :: OS Independent',
    ],
    python_requires='>=3.6',  # Minimum Python version required
)