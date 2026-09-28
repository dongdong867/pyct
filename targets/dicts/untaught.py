def check(config, name):
    config.keys() & {"a"}
    config[name] = 1
    (1, 2) in config
    str(config)
    return "done"
