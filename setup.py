from pathlib import Path
from setuptools import setup, find_packages

long_description = (Path(__file__).parent / "README.md").read_text(encoding="utf-8")

setup(
    name="savi-loop-guard",
    version="0.1.0",
    description="Zero-dependency detector for AI agents stuck in a loop",
    long_description=long_description,
    long_description_content_type="text/markdown",
    author="SAVI",
    author_email="contact@datagras.com",
    url="https://github.com/data-gras/savi-loop-guard",
    project_urls={
        "Bug Tracker": "https://github.com/data-gras/savi-loop-guard/issues",
        "Changelog":   "https://github.com/data-gras/savi-loop-guard/releases",
    },
    license="MIT",
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Programming Language :: Python :: 3.13",
        "Topic :: Software Development :: Libraries :: Python Modules",
        "Topic :: System :: Monitoring",
        "Topic :: Scientific/Engineering :: Artificial Intelligence",
    ],
    keywords=[
        "llm", "ai", "agent", "loop-detection", "circuit-breaker",
        "observability", "reliability", "savi",
    ],
    packages=find_packages(exclude=["tests*"]),
    python_requires=">=3.11",
    install_requires=[],
    extras_require={
        "dev": ["pytest>=8.2.0"],
    },
)
