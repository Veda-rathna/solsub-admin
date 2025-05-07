from mongoengine import (
    Document, 
    StringField, 
    DecimalField, 
    EmbeddedDocument, 
    EmbeddedDocumentListField,
    EmbeddedDocumentField,
    EmailField, 
    DateTimeField,
    BooleanField,
    IntField,
    ReferenceField
)

class BankDetails(EmbeddedDocument):
    bank_name = StringField()
    account_number = StringField()
    ifsc_code = StringField()
    branch_name = StringField()

class ClusterDetails(EmbeddedDocument):
    cluster_name = StringField(required=True, max_length=255)
    cluster_price = DecimalField(precision=2)
    timeline_days = IntField(min_value=1, max_value=30)  # Duration for paid period
    api_key = StringField(max_length=32)
    match_id_type = StringField(default='admin_generated', choices=('admin_generated', 'user_created'))
    trial_period = IntField(min_value=0, max_value=7, default=0)

class MatchId(Document):
    match_id = StringField(required=True, unique=True)
    cluster_name = StringField(required=True)
    created_on = DateTimeField(required=True)
    last_paid_on = DateTimeField(default=None, null=True)
    valid_till = DateTimeField(default=None, null=True)
    is_trial = BooleanField(default=False)
    
    meta = {
        'collection': 'match_ids',
        'indexes': ['match_id']
    }
    
    @classmethod
    def get_by_cluster(cls, cluster_name):
        return cls.objects(cluster_name=cluster_name).first()

class UserProfile(Document):
    user_id = StringField(required=True, unique=True)
    email = EmailField(required=True)
    username = StringField(required=True)
    created_at = DateTimeField(auto_now_add=True)
    bank_details = EmbeddedDocumentField(BankDetails)
    clusters = EmbeddedDocumentListField(ClusterDetails, default=[])

    meta = {
        'collection': 'users'
    }
    
    def add_cluster(self, cluster_data):
        new_cluster = ClusterDetails(**cluster_data)
        self.clusters.append(new_cluster)
        self.save()
    
    @classmethod
    def cluster_name_exists(cls, cluster_name):
        return cls.objects(clusters__cluster_name=cluster_name).first()

# Payment model to track payment history
class Payment(Document):
    payment_id = StringField(required=True, unique=True)
    match_id = StringField(required=True)
    api_key = StringField(required=True)
    amount = DecimalField(precision=2, required=True)
    status = StringField(choices=('Pending', 'Completed', 'Failed'), default='Pending')
    payment_date = DateTimeField(required=True)
    user_email = EmailField(required=False)
    
    meta = {
        'collection': 'payments',
        'indexes': ['payment_id', 'match_id', 'payment_date', 'api_key']
    }
    
    @property
    def cluster_name(self):
        """Get cluster name from api_key for backward compatibility"""
        for user in UserProfile.objects:
            for cluster in user.clusters:
                if cluster.api_key == self.api_key:
                    return cluster.cluster_name
        return None
