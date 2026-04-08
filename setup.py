#!/usr/bin/env python

"""The setup script."""

from setuptools import setup, find_packages

with open('README.md') as readme_file:
    readme = readme_file.read()

with open('HISTORY.md') as history_file:
    history = history_file.read()

with open('requirements.txt') as f:
    required = f.read().splitlines()

setup_requirements = ['pytest-runner', ]

test_requirements = ['pytest>=3', ]

setup(
    author="Juan Manuel Cristóbal Moreno",
    author_email='juanmcristobal',
    python_requires='>=3.10',
    classifiers=[
        'Intended Audience :: Developers',
        'Natural Language :: English',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.10',
        'Programming Language :: Python :: 3.11',
        'Programming Language :: Python :: 3.12',
        'Programming Language :: Python :: 3.13',
    ],
    description="Crawlsmith helps you craft reliable web crawlers in Python, combining page fetching, HTML parsing, link discovery, and content extraction into a simple and extensible toolkit.",
    entry_points={
        'console_scripts': [
            'crawlsmith=crawlsmith.cli:main',
        ],
    },
    install_requires=required,
    long_description=readme + '\n\n' + history,
    long_description_content_type='text/markdown',
    include_package_data=True,
    keywords='crawlsmith',
    name='crawlsmith',
    packages=find_packages(include=['crawlsmith', 'crawlsmith.*']),
    setup_requires=setup_requirements,
    test_suite='tests',
    tests_require=test_requirements,
    url='https://github.com/juanmcristobal/crawlsmith',
    version='0.1.0',
    zip_safe=False,
)
