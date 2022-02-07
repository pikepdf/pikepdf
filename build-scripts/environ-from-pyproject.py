import tomli

with open('pyproject.toml', 'rb') as f:
	t = tomli.load(f)
env = t['tool']['cibuildwheel']['environment']
print('\n'.join(f'{k}={v}' for k, v in env.items()))
