from rest_framework import serializers
from .models import PaymentPlanPDF, LetterToSelf
from DebtPlan.models import DebtPlan


class PaymentPlanPDFSerializer(serializers.ModelSerializer):
    pdf_url = serializers.SerializerMethodField()
    file_size_mb = serializers.SerializerMethodField()
    debt_plan_name = serializers.CharField(source='debt_plan.name', read_only=True)
    
    def get_pdf_url(self, obj):
        if obj.pdf_file:
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(obj.pdf_file.url)
            return obj.pdf_file.url
        return None
    
    def get_file_size_mb(self, obj):
        if obj.file_size:
            return round(obj.file_size / (1024 * 1024), 2)
        return 0
    
    class Meta:
        model = PaymentPlanPDF
        fields = [
            'id', 'debt_plan', 'debt_plan_name', 'pdf_url', 
            'generated_at', 'file_size', 'file_size_mb'
        ]
        read_only_fields = ['id', 'generated_at', 'file_size']


class LetterToSelfSerializer(serializers.ModelSerializer):
    debt_plan = serializers.PrimaryKeyRelatedField(
        queryset=DebtPlan.objects.all(),
        required=True,
        pk_field=serializers.UUIDField(format='hex_verbose')
    )
    debt_plan_name = serializers.CharField(source='debt_plan.name', read_only=True)
    
    class Meta:
        model = LetterToSelf
        fields = [
            'id', 'debt_plan', 'debt_plan_name', 'subject', 'body',
            'created_at', 'updated_at', 'is_sent', 'sent_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'is_sent', 'sent_at']
    
    def validate_debt_plan(self, value):
        """Ensure user can only create letters for their own debt plans"""
        request = self.context.get('request')
        if request and value.user != request.user:
            raise serializers.ValidationError(
                "Cannot create letter for another user's debt plan"
            )
        return value
    
    def validate_subject(self, value):
        if len(value) < 3:
            raise serializers.ValidationError("Subject must be at least 3 characters")
        return value
    
    def validate_body(self, value):
        if len(value) < 10:
            raise serializers.ValidationError("Letter body must be at least 10 characters")
        return value


class DebtPlanQuerySerializer(serializers.Serializer):
    """Query parameter for debt plan"""
    debt_plan = serializers.UUIDField(required=True)