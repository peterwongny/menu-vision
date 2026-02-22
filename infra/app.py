#!/usr/bin/env python3
import aws_cdk as cdk
from menu_vision_stack import MenuVisionStack

app = cdk.App()
MenuVisionStack(app, "MenuVisionStack")
app.synth()
