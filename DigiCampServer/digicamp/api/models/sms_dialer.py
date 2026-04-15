from django.db import models


'''
Sent status 
0 - Not sent
1 - In progress
4 - cancelled
5 - sent
'''

class SmsDialer(models.Model):
    phone_number = models.CharField(max_length=15, db_index=True)
    sent_status = models.IntegerField(null=True, blank=True, default=0, db_index=True)
    sent_datetime = models.DateTimeField(null=True, blank=True, default=None, db_index=True)
    user = models.ForeignKey('Users', on_delete=models.CASCADE, db_index=True)
    sms_campaign = models.ForeignKey('SmsCampaign', on_delete=models.CASCADE, db_index=True, null=True, blank=True)
    sms_template = models.ForeignKey('SmsTemplate', on_delete=models.CASCADE, db_index=True, null=True, blank=True)
    sms_through = models.CharField(max_length=10, db_index=True, null=True, blank=True)
    sms_sent = models.TextField(null=True, blank=True)
    sms_count = models.IntegerField(null=True, blank=True, default=0)
    class Meta:
        db_table = 'api_sms_dialer'    