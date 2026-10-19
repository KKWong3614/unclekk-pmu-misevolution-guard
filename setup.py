#!/usr/bin/env python3
"""PMU Misevolution Guard - Three-gate hard-block security harness"""
from setuptools import setup, find_packages
import os

# Read version from package.json
def get_version():
    pkg_json = os.path.join(os.path.dirname(__file__), 'package.json')
    if os.path.exists(pkg_json):
        import json
        with open(pkg_json, 'r', encoding='utf-8') as f:
            data = json.load(f)
            return data.get('version', '0.0.0')
    return '0.0.0'

# Read long description from README.md
def get_long_description():
    readme = os.path.join(os.path.dirname(__file__), 'README.md')
    if os.path.exists(readme):
        with open(readme, 'r', encoding='utf-8') as f:
            return f.read()
    return ''

setup(
    name='unclekk-pmu-misevolution-guard',
    version=get_version(),
    description='Three-gate hard-block security harness for Agent skill evolution',
    long_description=get_long_description(),
    long_description_content_type='text/markdown',
    author='unclekk',
    author_email='unclekk@sapiens-ai.com',
    license='MIT',
    keywords=['safety', 'guard', 'skill', 'evolution', 'security', 'three-gate'],
    url={
        'repository': 'https://github.com/unclekk/pmu-misevolution-guard',
        'issues': 'https://github.com/unclekk/pmu-misevolution-guard/issues',
    },
    packages=find_packages(where='scripts', exclude=['tests*']),
    package_dir={'': 'scripts'},
    python_requires='>=3.11',
    install_requires=[],
    extras_require={
        'test': ['pytest>=8.0.0'],
    },
    entry_points={
        'console_scripts': [
            'pmu-guard=pmu_guard:main',
        ],
    },
    classifiers=[
        'Development Status :: 4 - Beta',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: MIT License',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.11',
        'Programming Language :: Python :: 3.12',
        'Topic :: Security',
        'Topic :: Software Development :: Libraries :: Python Modules',
    ],
)