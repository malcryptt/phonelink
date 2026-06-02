from setuptools import setup

setup(
    name='phonelink-cli',
    version='1.0.0',
    description='Persistent USB Android connection tool for Linux, built for IoT and automation.',
    long_description=open('README.md').read(),
    long_description_content_type='text/markdown',
    author='malcryptt',
    url='https://github.com/malcryptt/phonelink',
    py_modules=['phonelink'],
    entry_points={
        'console_scripts': [
            'phonelink=phonelink:main',
        ],
    },
    classifiers=[
        'Programming Language :: Python :: 3',
        'License :: OSI Approved :: MIT License',
        'Operating System :: POSIX :: Linux',
        'Topic :: Utilities',
    ],
    python_requires='>=3.6',
)
