
def str_to_bool(env_val):
    '''
    Simple means to convert str to bool. 
    '''
    if env_val in ['True', 'true', 1]:
        return True
    
    return False
