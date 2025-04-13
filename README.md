# PaperPi-Web

Rewrite of PaperPi to support web configuration and customization

## Developing for PaperPi

### Create a PyEnv

It is recommended to install `pyenv` to avoid breaking the system python install on a Raspi. This isn't strictly necessary, but makes everything a lot easier to get rolling.

1. Install required packages: 
```
sudo apt-get update; sudo apt-get install make build-essential libssl-dev zlib1g-dev \
libbz2-dev libreadline-dev libsqlite3-dev wget curl llvm \
libncursesw5-dev xz-utils tk-dev libxml2-dev libxmlsec1-dev libffi-dev liblzma-dev
```
2. Automagically install pyenv in your user environement: `curl https://pyenv.run | bash`
2. Relaunch your shell (log out/login)
3. Create a pyenv for the current user: `pyenv install 3.11.2 `
4. Set the env as the global default: `pyenv global 3.11.2`


### Set Up Development Environment

1. Clone the repo: `$ git clone --recurse-submodules https://github.com/txoof/PaperPi-Web.git`
2. Change to the repo directory: `cd ./PaperPi-Web`
2. Create a virtualenv in the project directory: `$ ./pyenv_utilities -c`
    - Optionally create a jupyter environment and install the kernel: `$ ./pyenv_utilities -j`. See Jupyter section below.
4. Activate project venv: `$ source ./venv_activate`
5. Install requirements: `$ pip3 install requirements.txt`

### Working in Jupyter

Jupyter allows for previewing output of code within a browser. It's a quick way to see exactly what's going on in the ouptut without waiting for the display to be updated. This is completely optional, but can be quite helpful. Jupyter notebook, at its most basic creates a nice web interface for working on `.ipynb` files. Jupyter Lab provides more utilities and functionality.

Jupyter Notebook can be installed with the debian package `jupyter`

Jupyter Lab can be installed in with pip, this is best done in a pyenv virtualenv: `pip install jupyterlab`

The Jupy-Text module is recommended for automagically converting `.ipynb` into `.py`. With the project venv active: `pip install jupytext`

To work in a Jupyter Notebook, take the following steps:

1. Launch Jupyter with an external IP:
    - Jupyter Lab: `myHost=$(hostname -I | cut -d " " -f 1); jupyter-lab --ip=$myHost --no-browser`
    - Jupyter Notebook: `myHost=$(hostname -I | cut -d " " -f 1); jupyter-notebook --ip=$myHost --no-browser`
2. Connect via your web browser at the provided link e.g. `http://192.168.1.172:8888/?token=fab029f37deadbeef`
    - NOTE: VS Code can connect to this remote sever, but there are issues with relative imports functioning properly. This is not recommended.
3. Navigate to the project folder and launch an `.ipynb` file. 
4. Use the drop down menu in the top right corner to select the kernel that matches this project.

#### Tips

- Connect with ssh to your pi and use `tmux` to keep your ssh sessions alive. Tmux allows you to open multiple remote ssh sessions from the same login and keeps those sessions open indefinitely
    - `ssh -t  pi@192.168.1.10 "tmux -CC new -A -s myshell"
    - Reconnect to existing sessions using the same command.
- Mac OS users: [iTerm2 has built in TMUX support. ](https://iterm2.com/documentation-tmux-integration.html). Set it up once and you can connect automatically using tmux and create new windows with CMD+N or split existing windows with CMD+SHIFT+D
    - Use the command above as the profile command.

## Plugins

### PluginManager

The plugin manger loads plugins based on the `paperpi_plugins.yaml`.

#### Active Plugins

Active display all the time

#### Dormant Plugins

Dormant only display when required (e.g. now playing information)

