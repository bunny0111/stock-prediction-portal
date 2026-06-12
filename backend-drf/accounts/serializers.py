from django.contrib.auth.models import User
from rest_framework import serializers

class UserSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=8, style={'input_type': 'password'})
    class Meta:
        model = User
        fields = ['username', 'email', 'password']

    def create(self, validated_data):
        # User.objects.create = Save the password in plain text, which is not secure. Instead, we should use create_user to hash the password.
        # User.objects.create_user = This method will hash the password before saving it to the database, ensuring that the password is stored securely.
        user = User.objects.create_user(
            validated_data['username'],
            validated_data['email'],
            validated_data['password']
        )
        # user = User.objects.create_user(**validated_data)
        return user