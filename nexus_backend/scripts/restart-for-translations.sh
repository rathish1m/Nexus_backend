#!/bin/bash

# Script pour redémarrer le serveur Django après mise à jour des traductions
# Usage: ./scripts/restart-for-translations.sh

cd "$(dirname "$0")/.."

echo "🔄 Arrêt des serveurs Django en cours..."
# Arrêter les serveurs Django existants
pkill -f "manage.py runserver" || true

echo "📝 Recompilation des traductions..."
# Recompiler les traductions
python manage.py compilemessages

echo "⏱️  Attente de 2 secondes..."
sleep 2

echo "🚀 Redémarrage du serveur Django..."
# Redémarrer le serveur en arrière-plan
python manage.py runserver &

echo "⏱️  Attente de 5 secondes pour que le serveur démarre..."
sleep 5

echo ""
echo "✅ Le serveur Django a été redémarré avec les nouvelles traductions"
echo ""
echo "📋 Instructions pour tester:"
echo "1. Ouvrez votre navigateur"
echo "2. Allez sur /fr/client/billing/?pay=now"
echo "3. Vérifiez que le texte \"You'll be notified before the due date\" est maintenant en français"
echo "4. Le texte devrait afficher: \"Vous serez notifié avant la date d'échéance.\""
echo ""
echo "🔍 Pour vérifier l'état du serveur:"
echo "   ps aux | grep 'manage.py runserver'"
echo ""
echo "🛑 Pour arrêter le serveur:"
echo "   pkill -f 'manage.py runserver'"
