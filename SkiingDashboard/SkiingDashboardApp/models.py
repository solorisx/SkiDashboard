from django.db import models

# Create your models here.

class Activity(models.Model):
    name = models.CharField(max_length=30)
    #todo: all activity level data
    #todo: 1:n segments
    on_delete=models.CASCADE
    
class Segment(models.Model):
    downhill = models.BooleanField
    #todo: all lap level data
    

