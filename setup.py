#!/usr/bin/env python3

from setuptools import setup, find_packages

setup(
    name='uHTTP',
    version='1.0.0',
    py_modules=['uhttp'],
    author='gus',
    author_email='0x67757300@gmail.com',
    license='MIT',
    platforms='any',
    description='ASGI micro framework',
    long_description=open('README.md').read(),
    long_description_content_type='text/markdown',
    url='https://github.com/0x67757300/uHTTP',
    classifiers=[
        'Programming Language :: Python :: 3',
    ],
)
