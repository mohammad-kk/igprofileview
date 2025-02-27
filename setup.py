from setuptools import setup, find_packages

setup(
    name="igprofileviewer",
    version="0.1",
    packages=find_packages(),
    install_requires=[
        'Flask==2.3.3',
        'requests==2.31.0',
        'python-dotenv==1.0.0',
        'gunicorn==21.2.0',
        'supabase==2.3.1',
        'asgiref==3.7.2',
        'aiohttp==3.8.5',
        'typing-extensions==4.7.1',
    ],
)