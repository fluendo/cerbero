import os
import sys
from setuptools import setup, find_packages
from cerbero.enums import CERBERO_VERSION

sys.path.insert(0, './cerbero')


# Utility function to read the README file.
def read(fname):
    return open(os.path.join(os.path.dirname(__file__), fname)).read()


setup(
    name='cerbero',
    version=CERBERO_VERSION,
    author='Andoni Morales',
    author_email='amorales@fluendo.com',
    description=('Multi platform build system for Open Source projects'),
    license='LGPL',
    url='http://gstreamer.freedesktop.org/',
    packages=[
        'cerbero-share.config',
        'cerbero-share.data',
        'cerbero-share.packages',
        'cerbero-share.recipes',
    ]
    + find_packages(exclude=['config', 'data', 'packages', 'recipes', 'test']),
    package_dir={
        'cerbero-share.config': 'config',
        'cerbero-share.data': 'data',
        'cerbero-share.packages': 'packages',
        'cerbero-share.recipes': 'recipes',
    },
    package_data={
        'cerbero-share.config': ['**'],
        'cerbero-share.data': ['**'],
        'cerbero-share.packages': ['**'],
        'cerbero-share.recipes': ['**'],
    },
    long_description=read('README.md'),
    zip_safe=False,
    include_package_data=True,
    entry_points="""
        [console_scripts]
        cerbero = cerbero.main:main""",
    classifiers=[
        'License :: OSI Approved :: LGPL License',
    ],
)
