import toml

t = toml.load('pyproject.toml')
env = t['tool']['cibuildwheel']['environment']
print('\n'.join(f'{k}={v}' for k, v in env.items()))
