"""Operator outcomes keep write acknowledgment separate from observed effect."""
def command_status(receipt):
    state=receipt['state']
    if state in ('VERIFIED','VERIFIED_READBACK','VERIFIED_SIMULATED','EFFECT_OBSERVED','COMPLETED_OBSERVED','COMPLETED_SIMULATED'):
        return '✓','Command effect verified','#39c6a4'
    if state=='REJECTED':return '×','Command not sent','#f27778'
    if state in ('UNKNOWN','FAILED','NOT_VERIFIED'):
        return ('!','Command effect not verified — acknowledgment received','#f27778') if receipt.get('reply_received') else ('×','No valid command acknowledgment','#f27778')
    if receipt.get('reply_received'):return '●','Command acknowledged — effect unconfirmed','#69a7ed'
    return '…','Checking command / waiting for acknowledgment','#efb753'
